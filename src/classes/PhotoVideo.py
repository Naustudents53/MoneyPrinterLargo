from __future__ import annotations

import base64
import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal
from uuid import uuid4

import requests
from moviepy.editor import AudioFileClip
from PIL import Image, ImageOps

from config import (
    ROOT_DIR,
    get_gemini_api_key,
    get_gemini_models,
    get_openai_api_key,
    get_openai_base_url,
    get_openai_models,
    resolve_series,
)
from status import info, success, warning
from cache import get_temp_cache_path
from upload_tracker import record_generation
from utils import (
    expand_regnal_numerals_tracked,
    expand_spanish_numbers,
    expand_spoken_symbols,
    restore_regnal_numerals_in_timestamps,
)

from .Retention import CosmicRetentionEngine
from .NarrationVoice import NarrationVoice
from .MaxRetention import MaxRetentionEngine, is_max_retention
from .Tts import LONG_VIDEO_NARRATOR, TTS
from .YouTube import LONG_VIDEO_SECTION_THEMES, YouTube


PhotoVideoKind = Literal["short", "long"]

SUPPORTED_PHOTO_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


@dataclass
class PhotoVideoRequest:
    """Input for the uploaded-photos video pipeline."""

    kind: PhotoVideoKind = "short"
    photo_paths: list[str] = field(default_factory=list)
    topic: str = ""
    script: str = ""
    auto_analyze: bool = True


@dataclass
class PhotoAnalysis:
    """Compact semantic brief derived from the uploaded photos."""

    topic: str = ""
    story_angle: str = ""
    photo_notes: list[str] = field(default_factory=list)
    raw: str = ""

    def notes_text(self) -> str:
        lines = []
        if self.story_angle:
            lines.append(f"Story angle: {self.story_angle}")
        for idx, note in enumerate(self.photo_notes, 1):
            lines.append(f"Photo {idx}: {note}")
        return "\n".join(lines).strip()


def collect_photo_paths(inputs: str | Iterable[str]) -> list[str]:
    """Resolve files/directories into an ordered list of supported image paths."""
    if isinstance(inputs, str):
        parts = [p.strip().strip('"') for p in re.split(r"[\n;,]+", inputs) if p.strip()]
    else:
        parts = [str(p).strip().strip('"') for p in inputs if str(p).strip()]

    resolved: list[str] = []
    for part in parts:
        path = Path(part).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
                if child.is_file() and child.suffix.lower() in SUPPORTED_PHOTO_EXTENSIONS:
                    resolved.append(str(child.resolve()))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_PHOTO_EXTENSIONS:
            resolved.append(str(path.resolve()))

    deduped: list[str] = []
    seen = set()
    for path in resolved:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def _extract_json_object(text: str) -> dict:
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strip_wrapping_quotes(text: str) -> str:
    return re.sub(r'^[\s"\'`]+|[\s"\'`]+$', "", text or "").strip()


class PhotoVideoGenerator:
    """
    Orchestrates a complete video from user-uploaded photos.

    This is intentionally a composition layer around the existing YouTube
    class. It reuses the project's LLM, metadata, TTS, Ken Burns, karaoke,
    music, sidecar, upload tracking and upload flow without subclassing the
    provider implementation.
    """

    def __init__(self, youtube: YouTube) -> None:
        self.youtube = youtube

    def generate(self, tts_instance: TTS, request: PhotoVideoRequest) -> str:
        kind = (request.kind or "short").strip().lower()
        if kind not in {"short", "long"}:
            raise ValueError("Photo video kind must be 'short' or 'long'")

        photo_paths = collect_photo_paths(request.photo_paths)
        if not photo_paths:
            raise ValueError("No valid uploaded photos were provided")

        self._reset_video_state(is_long=(kind == "long"))
        self.youtube.images = self.prepare_photo_assets(photo_paths)
        self.youtube.image_prompts = [Path(p).stem for p in photo_paths]

        analysis = PhotoAnalysis()
        needs_photo_analysis = request.auto_analyze and (
            not request.topic.strip() or not request.script.strip()
        )
        if needs_photo_analysis:
            analysis = self.analyze_photos(
                kind=kind,
                photo_paths=self.youtube.images,
                user_topic=request.topic,
            )

        self.youtube.subject = self._resolve_subject(request, analysis)
        self.youtube.script = self._resolve_script(kind, request, analysis)

        if kind == "short":
            return self._generate_short_from_uploaded_photos(tts_instance)
        return self._generate_long_from_uploaded_photos(tts_instance)

    def prepare_photo_assets(self, photo_paths: Iterable[str]) -> list[str]:
        """
        Copy uploaded photos into scratch space as normalized RGB JPEGs.

        MoviePy handles many formats, but normalizing orientation and color
        mode here prevents EXIF rotation and alpha-channel surprises during
        render.
        """
        mp_dir = Path(get_temp_cache_path(ROOT_DIR))
        mp_dir.mkdir(parents=True, exist_ok=True)

        prepared: list[str] = []
        for raw_path in photo_paths:
            path = Path(raw_path)
            if not path.is_file():
                raise FileNotFoundError(f"Photo not found: {raw_path}")
            if path.suffix.lower() not in SUPPORTED_PHOTO_EXTENSIONS:
                raise ValueError(f"Unsupported photo format: {raw_path}")

            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                if img.mode not in {"RGB", "L"}:
                    img = img.convert("RGB")
                elif img.mode == "L":
                    img = img.convert("RGB")

                out_path = mp_dir / f"{uuid4()}.jpg"
                img.save(out_path, "JPEG", quality=94, optimize=True)
                prepared.append(str(out_path))

        success(f"Prepared {len(prepared)} uploaded photos.")
        return prepared

    def analyze_photos(
        self,
        *,
        kind: PhotoVideoKind,
        photo_paths: list[str],
        user_topic: str = "",
    ) -> PhotoAnalysis:
        prompt = self._photo_analysis_prompt(kind, photo_paths, user_topic)

        for provider_name, fn in (
            ("Gemini vision", self._analyze_with_gemini_vision),
            ("OpenAI vision", self._analyze_with_openai_vision),
        ):
            try:
                raw = fn(prompt, photo_paths)
                analysis = self._parse_analysis(raw)
                if analysis.topic or analysis.photo_notes:
                    info(f" => Photo analysis: {provider_name}")
                    return analysis
            except Exception as exc:
                if str(exc):
                    warning(f"{provider_name} unavailable: {str(exc)[:180]}")

        warning("Vision analysis was not available; using filenames and dimensions as a fallback.")
        raw = self.youtube.generate_response(
            self._metadata_only_analysis_prompt(kind, photo_paths, user_topic)
        )
        return self._parse_analysis(raw)

    def _resolve_subject(self, request: PhotoVideoRequest, analysis: PhotoAnalysis) -> str:
        if request.topic.strip():
            return request.topic.strip()
        if analysis.topic.strip():
            return analysis.topic.strip()
        if request.script.strip():
            topic = self._derive_topic_from_script(request.script)
            if topic:
                return topic
        return "Video basado en fotos subidas"

    def _resolve_script(
        self,
        kind: PhotoVideoKind,
        request: PhotoVideoRequest,
        analysis: PhotoAnalysis,
    ) -> str:
        if request.script.strip():
            return request.script.strip()

        notes = analysis.notes_text()
        if notes:
            script = self._generate_script_from_photo_analysis(kind, notes)
            if script:
                return script

        if kind == "short":
            self.youtube.generate_script()
        else:
            self.youtube.generate_long_script()
        return self.youtube.script

    def _generate_short_from_uploaded_photos(self, tts_instance: TTS) -> str:
        self.youtube._is_long_video = False
        self.youtube.generate_metadata()
        self.youtube.generate_script_to_speech(tts_instance)
        path = self.youtube.combine()
        self._finish_generation(path, is_long=False)
        success(f"Uploaded-photos Short generated: {path}")
        return path

    def _generate_long_from_uploaded_photos(self, tts_instance: TTS) -> str:
        self.youtube._is_long_video = True
        self.youtube.active_series, self.youtube.subject = resolve_series(self.youtube.subject)
        if self.youtube.active_series:
            info(f" => Series: {self.youtube.active_series.get('id', '')}")

        self.youtube.generate_long_metadata()
        try:
            self.youtube.generate_thumbnail()
        except Exception as exc:
            warning(f"Thumbnail generation failed: {str(exc)[:200]} (upload will continue without custom thumbnail)")
            self.youtube.thumbnail_path = ""

        self._synthesize_long_with_word_timestamps(tts_instance)
        path = self.youtube.combine_long()
        self._finish_generation(path, is_long=True)
        success(f"Uploaded-photos long video generated: {path}")
        return path

    def _finish_generation(self, path: str, *, is_long: bool) -> None:
        self.youtube.video_path = os.path.abspath(path)
        build_retention_plan = getattr(self.youtube, "_build_retention_plan", None)
        if not is_long and callable(build_retention_plan):
            build_retention_plan(self.youtube.video_path)
        self.youtube._persist_metadata_sidecar(is_long=is_long)
        try:
            record_generation(
                self.youtube.video_path,
                list(self.youtube.images),
                [getattr(self.youtube, "tts_path", None), getattr(self.youtube, "subtitles_path", None)],
                subject=getattr(self.youtube, "subject", "") or "",
            )
        except Exception as exc:
            warning(f"Could not record upload manifest: {exc}")
        persist_retention_plan = getattr(self.youtube, "_persist_retention_plan", None)
        if not is_long and callable(persist_retention_plan):
            persist_retention_plan()

    def _reset_video_state(self, *, is_long: bool) -> None:
        self.youtube.images = []
        self.youtube.image_prompts = []
        self.youtube.word_timestamps = None
        self.youtube.tts_path = None
        self.youtube.subtitles_path = None
        self.youtube.thumbnail_path = ""
        self.youtube._used_stock_urls = set()
        self.youtube._is_long_video = is_long
        self.youtube.retention_plan = {}
        self.youtube.retention_preflight = {}
        self.youtube.retention_hook_lab = {}
        self.youtube.visual_beat_map = []
        self.youtube.visual_beat_report = {}
        self.youtube.visual_preflight = {}

    def _photo_analysis_prompt(
        self,
        kind: PhotoVideoKind,
        photo_paths: list[str],
        user_topic: str,
    ) -> str:
        manifest = self._photo_manifest(photo_paths)
        user_topic_line = user_topic.strip() or "(none - infer it from the photos)"
        return f"""You are analyzing user-uploaded photos to build a complete YouTube {kind} video.

Channel niche: {self.youtube.niche}
Channel language: {self.youtube.language}
User topic, if any: {user_topic_line}
Photo manifest:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

Analyze the visible content, sequence, mood, people/objects/places, and the strongest story angle across the photos.

Return ONLY a JSON object with these fields:
{{
  "topic": "one focused YouTube topic in the channel language",
  "story_angle": "one paragraph explaining the narrative angle that connects the photos",
  "photo_notes": ["one concrete description per photo, in order"]
}}

Rules:
- If the user supplied a topic, keep the topic aligned with it.
- Do not invent exact identities, names, places, dates, or claims that are not visible or strongly implied.
- Write every field in {self.youtube.language}.
- No markdown, no code fences, no commentary outside JSON."""

    def _metadata_only_analysis_prompt(
        self,
        kind: PhotoVideoKind,
        photo_paths: list[str],
        user_topic: str,
    ) -> str:
        manifest = self._photo_manifest(photo_paths)
        user_topic_line = user_topic.strip() or "(none)"
        return f"""Vision analysis is unavailable. Infer the best possible YouTube {kind} topic from this uploaded-photo manifest.

Channel niche: {self.youtube.niche}
Channel language: {self.youtube.language}
User topic, if any: {user_topic_line}
Photo manifest:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

Return ONLY JSON:
{{
  "topic": "one focused YouTube topic in the channel language",
  "story_angle": "one paragraph based only on filenames, dimensions and ordering",
  "photo_notes": ["one cautious note per photo, in order"]
}}"""

    def _generate_script_from_photo_analysis(self, kind: PhotoVideoKind, notes: str) -> str:
        if kind == "short":
            sentence_length = (
                getattr(self.youtube, "_sentence_length_override", None)
                or self._safe_short_sentence_length()
            )
            target_words = getattr(self.youtube, "_target_word_count", None)
            target_clause = (
                f"Aim for about {target_words} spoken words total."
                if target_words else
                "Keep the pacing suitable for a 45-75 second Short."
            )
            directive = CosmicRetentionEngine.short_generation_directive(
                self.youtube.subject,
                self.youtube.niche,
                self.youtube.language,
            )
            max_directive = (
                MaxRetentionEngine.script_generation_directive(
                    self.youtube.subject,
                    self.youtube.niche,
                    self.youtube.language,
                    sentence_length,
                )
                if is_max_retention(getattr(self.youtube, "_retention_mode", ""))
                else ""
            )
            voice_directive = NarrationVoice.short_generation_directive(self.youtube.language)
            prompt = f"""Write a narration script for a YouTube Short made only with the user's uploaded photos.

Topic: {self.youtube.subject}
Channel niche: {self.youtube.niche}
Photo analysis:
{notes}

Requirements:
- EXACTLY {sentence_length} sentences.
- {target_clause}
- Use the uploaded photos as the visual backbone, but do NOT say "photo", "image", "in this picture", or any stage direction.
- No title, no bullet list, no markdown, no labels.
- No welcome, no meta commentary, no calls to action.
- Write in {self.youtube.language}.
{directive}
{max_directive}
{voice_directive}

Return ONLY the narration script."""
            script = _strip_wrapping_quotes(self.youtube.generate_response(prompt))
            script = self.youtube._clean_llm_script(script)
            script = CosmicRetentionEngine.optimize_short_script(
                script=script,
                topic=self.youtube.subject,
                niche=self.youtube.niche,
                language=self.youtube.language,
                sentence_length=sentence_length,
                generate_response=self.youtube.generate_response,
                target_words=target_words,
            )
            if is_max_retention(getattr(self.youtube, "_retention_mode", "")):
                script = MaxRetentionEngine.optimize_short_script(
                    script=script,
                    topic=self.youtube.subject,
                    niche=self.youtube.niche,
                    language=self.youtube.language,
                    sentence_length=sentence_length,
                    generate_response=self.youtube.generate_response,
                    target_words=target_words,
                )
                script = self.youtube._run_max_retention_preflight(
                    script,
                    sentence_length=sentence_length,
                    allow_rewrite=True,
                )
            return script.strip()

        themes = CosmicRetentionEngine.long_section_themes(
            LONG_VIDEO_SECTION_THEMES,
            self.youtube.subject,
            self.youtube.niche,
        )
        theme_text = "\n".join(f"{idx + 1}. {theme}" for idx, theme in enumerate(themes))
        directive = CosmicRetentionEngine.long_generation_directive(
            self.youtube.subject,
            self.youtube.niche,
            self.youtube.language,
        )
        voice_directive = NarrationVoice.long_generation_directive(self.youtube.language)
        prompt = f"""Write a complete long-form YouTube narration script using the uploaded photos as the visual backbone.

Topic: {self.youtube.subject}
Channel niche: {self.youtube.niche}
Photo analysis:
{notes}

Narrative section plan:
{theme_text}

Requirements:
- 2200 to 3200 spoken words.
- Documentary tone with a strong cold open, clear progression, and memorable ending.
- Use the details from the uploaded photos as anchors, but do NOT include stage directions.
- No markdown tables, no bullet lists, no image prompts, no narrator labels.
- Write only narration that can be read aloud by TTS.
- Write in {self.youtube.language}.
{directive}
{voice_directive}

Return ONLY the narration script."""
        script = _strip_wrapping_quotes(self.youtube.generate_response(prompt, temperature=0.75))
        return self.youtube._postprocess_long_script(script)

    def _derive_topic_from_script(self, script: str) -> str:
        prompt = f"""Create one concise YouTube topic/title from this narration script.

Language: {self.youtube.language}
Script:
\"\"\"
{script[:2500]}
\"\"\"

Return only the topic, under 90 characters. No quotes."""
        try:
            return _strip_wrapping_quotes(self.youtube.generate_response(prompt))
        except Exception:
            return ""

    def _synthesize_long_with_word_timestamps(self, tts_instance: TTS) -> str:
        path = os.path.join(get_temp_cache_path(ROOT_DIR), str(uuid4()) + ".wav")
        tts_script = self.youtube._clean_script_for_tts(self.youtube.script)
        if not tts_script or len(tts_script.split()) < 50:
            warning("TTS cleaning removed too much content, using raw script")
            tts_script = re.sub(r"\[.*?\]", "", self.youtube.script).strip()

        tts_script = expand_spoken_symbols(tts_script)
        tts_text, regnal_subs = expand_regnal_numerals_tracked(tts_script)
        tts_text = expand_spanish_numbers(tts_text)

        long_vid = self.youtube._resolve_voice(getattr(self.youtube, "_long_voice", "")) or LONG_VIDEO_NARRATOR
        lang = (getattr(self.youtube, "_language", "") or "").strip().lower()
        is_spanish = lang.startswith("esp") or lang in {"es", "spanish"}
        if is_spanish and not long_vid.lower().startswith("es-"):
            warning(
                f"Voice '{long_vid}' is not Spanish but channel language is "
                f"'{self.youtube.language}'. Falling back to {LONG_VIDEO_NARRATOR}."
            )
            long_vid = LONG_VIDEO_NARRATOR

        info(f" => Using long-video voice: {long_vid}")
        audio_path, word_timestamps = tts_instance.synthesize_with_timestamps(
            tts_text,
            path,
            voice_id=long_vid,
            rate="-8%",
            pitch="-15Hz",
        )
        if word_timestamps:
            word_timestamps = restore_regnal_numerals_in_timestamps(word_timestamps, regnal_subs)
        self.youtube.word_timestamps = word_timestamps
        self.youtube.tts_path = audio_path

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            audio_dur = AudioFileClip(audio_path).duration
            info(f" => Audio duration: {audio_dur:.0f} seconds ({audio_dur / 60:.1f} min)")
            return audio_path
        raise RuntimeError(f"TTS failed to generate audio file at {audio_path}")

    def _photo_manifest(self, photo_paths: list[str]) -> list[dict]:
        manifest: list[dict] = []
        for idx, raw_path in enumerate(photo_paths, 1):
            path = Path(raw_path)
            item = {
                "index": idx,
                "filename": path.name,
                "stem": path.stem,
                "suffix": path.suffix.lower(),
            }
            try:
                with Image.open(path) as img:
                    item.update({
                        "width": img.width,
                        "height": img.height,
                        "aspect_ratio": round(img.width / img.height, 4) if img.height else 0,
                    })
                    exif = getattr(img, "getexif", lambda: {})()
                    if exif:
                        # 306 DateTime, 36867 DateTimeOriginal.
                        taken = exif.get(36867) or exif.get(306)
                        if taken:
                            item["exif_datetime"] = str(taken)
            except Exception as exc:
                item["read_error"] = str(exc)[:120]
            manifest.append(item)
        return manifest

    def _parse_analysis(self, raw: str) -> PhotoAnalysis:
        data = _extract_json_object(raw)
        notes = data.get("photo_notes") or []
        if isinstance(notes, str):
            notes = [n.strip() for n in re.split(r"\n+|\s*\|\s*", notes) if n.strip()]
        if not isinstance(notes, list):
            notes = []
        return PhotoAnalysis(
            topic=str(data.get("topic", "") or "").strip(),
            story_angle=str(data.get("story_angle", "") or "").strip(),
            photo_notes=[str(n).strip() for n in notes if str(n).strip()],
            raw=raw or "",
        )

    def _analyze_with_gemini_vision(self, prompt: str, photo_paths: list[str]) -> str:
        api_key = get_gemini_api_key()
        if not api_key:
            raise RuntimeError("No Gemini API key configured")

        try:
            from llm_provider import normalize_gemini_model_id
        except Exception:
            normalize_gemini_model_id = lambda m: m  # noqa: E731

        models = [normalize_gemini_model_id(m) for m in get_gemini_models()]
        if not models:
            raise RuntimeError("No Gemini model configured")

        parts = [{"text": prompt}]
        for path in photo_paths[:10]:
            mime_type, payload = self._image_part(path)
            parts.append({"inline_data": {"mime_type": mime_type, "data": payload}})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.35},
        }

        last_error = None
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                response = requests.post(url, json=body, timeout=180)
                response.raise_for_status()
                data = response.json()
                parts_out = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts_out).strip()
                if text:
                    return text
                last_error = RuntimeError("Gemini returned empty vision analysis")
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"All Gemini vision models failed: {last_error}")

    def _analyze_with_openai_vision(self, prompt: str, photo_paths: list[str]) -> str:
        api_key = get_openai_api_key()
        if not api_key:
            raise RuntimeError("No OpenAI API key configured")

        content = [{"type": "input_text", "text": prompt}]
        for path in photo_paths[:10]:
            mime_type, payload = self._image_part(path)
            content.append({
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{payload}",
            })

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        models = get_openai_models()
        last_error = None
        for model in models:
            body = {
                "model": model,
                "input": [{"role": "user", "content": content}],
                "store": False,
            }
            try:
                response = requests.post(
                    f"{get_openai_base_url().rstrip('/')}/responses",
                    headers=headers,
                    json=body,
                    timeout=180,
                )
                response.raise_for_status()
                text = self._extract_openai_response_text(response.json())
                if text:
                    return text
                last_error = RuntimeError("OpenAI returned empty vision analysis")
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"All OpenAI vision models failed: {last_error}")

    def _image_part(self, path: str) -> tuple[str, str]:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88, optimize=True)
        # We always encode to JPEG above, so the inline MIME type must match
        # the transformed payload rather than the original file extension.
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode("ascii")

    @staticmethod
    def _extract_openai_response_text(data: dict) -> str:
        chunks: list[str] = []
        for item in data.get("output", []) or []:
            if isinstance(item, dict):
                for content in item.get("content", []) or []:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") in {"output_text", "text"}:
                        chunks.append(str(content.get("text", "")))
        if chunks:
            return "\n".join(c for c in chunks if c).strip()
        direct = data.get("output_text")
        return str(direct or "").strip()

    @staticmethod
    def _safe_short_sentence_length() -> int:
        try:
            from config import get_script_sentence_length
            return int(get_script_sentence_length())
        except Exception:
            return 4
