"""
Movie Summary pipeline.

Takes a movie title, searches and downloads it via yt-dlp, transcribes the
audio with Whisper, asks an LLM to produce a chronological recap plan
(opening hook + body clips + thumbnail timestamp), cuts those clips from the
source, narrates each with TTS over an 8% bed of the original audio, and
assembles a single MP4 of <= 20 minutes ready for the inherited
`YouTube.upload_video()` Selenium flow.

The user is responsible for fair-use / public-domain compliance. The 8%
audio mix reduces but does not eliminate Content-ID matches.
"""

import json
import os
import re
import subprocess
from typing import List, Optional
from uuid import uuid4

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import (
    ROOT_DIR,
    get_long_video_llm_model,
    get_movie_chunk_minutes,
    get_movie_download_format,
    get_movie_hook_seconds,
    get_movie_max_clip_seconds,
    get_movie_max_duration_seconds,
    get_movie_min_clip_seconds,
    get_movie_original_audio_volume,
    get_stt_provider,
    get_threads,
    get_verbose,
    get_whisper_compute_type,
    get_whisper_device,
    get_whisper_model,
)
from llm_provider import force_provider, generate_text, warmup_ollama_model
from status import error, info, success, warning

from .Tts import LONG_VIDEO_NARRATOR, TTS
from .YouTube import YouTube


class PlanValidationError(Exception):
    """Raised when the LLM-produced plan fails timestamp / structure checks."""


HOOK_FORBIDDEN_BEAT_TYPES = {"climax", "resolution"}
ALL_BEAT_TYPES = {"setup", "plot_twist", "death", "reveal", "climax", "resolution"}


class MovieSummary(YouTube):
    """
    Movie recap generator. Subclasses YouTube to inherit the upload flow,
    metadata generation, and thumbnail rendering. Overrides the asset
    production: source = movie clips instead of AI-generated images.
    """

    # ---------- Step 1: download ----------

    def download_movie(self, title: str, archive_identifier: Optional[str] = None) -> str:
        """
        Download the source movie. If `archive_identifier` is given, fetches
        from archive.org via yt-dlp's native archive.org extractor. Otherwise
        falls back to a YouTube search.
        Returns the path to the downloaded MP4.
        """
        if archive_identifier:
            return self._download_from_archive_org(archive_identifier)
        return self._download_from_youtube_search(title)

    def _download_from_archive_org(self, identifier: str) -> str:
        import yt_dlp

        url = f"https://archive.org/details/{identifier}"
        out_path = os.path.join(ROOT_DIR, ".mp", f"movie_{uuid4()}.%(ext)s")
        info(f"\n[Movie] Downloading from archive.org: {url}")
        ydl_opts = {
            # archive.org items vary in available formats; this picks the best
            # MP4 available, then any best video as fallback.
            "format": "best[ext=mp4]/best",
            "outtmpl": out_path,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": not get_verbose(),
            "no_warnings": not get_verbose(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            if not result:
                raise RuntimeError(f"yt-dlp returned no result for archive id '{identifier}'")
            entries = result.get("entries") or [result]
            if not entries:
                raise RuntimeError(f"yt-dlp returned no entries for archive id '{identifier}'")
            downloaded = ydl.prepare_filename(entries[0])
            base, _ = os.path.splitext(downloaded)
            mp4_path = base + ".mp4"
            if not os.path.isfile(mp4_path):
                mp4_path = downloaded
            success(f"[Movie] Downloaded: {mp4_path}")
            return mp4_path

    def _download_from_youtube_search(self, title: str) -> str:
        import yt_dlp

        out_path = os.path.join(ROOT_DIR, ".mp", f"movie_{uuid4()}.%(ext)s")
        query = f"ytsearch1:{title} película completa"

        info(f"\n[Movie] Searching: {query}")
        ydl_opts = {
            "format": get_movie_download_format(),
            "outtmpl": out_path,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": not get_verbose(),
            "no_warnings": not get_verbose(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(query, download=True)
            if not result:
                raise RuntimeError(f"yt-dlp returned no result for '{title}'")
            entries = result.get("entries") or [result]
            if not entries:
                raise RuntimeError(f"yt-dlp returned no entries for '{title}'")
            downloaded = ydl.prepare_filename(entries[0])
            base, _ = os.path.splitext(downloaded)
            mp4_path = base + ".mp4"
            if not os.path.isfile(mp4_path):
                mp4_path = downloaded
            success(f"[Movie] Downloaded: {mp4_path}")
            return mp4_path

    # ---------- Step 2: extract audio ----------

    def extract_audio(self, video_path: str) -> str:
        """Extract a WAV track from the source video for Whisper."""
        out_wav = os.path.join(ROOT_DIR, ".mp", f"audio_{uuid4()}.wav")
        info(f"[Movie] Extracting audio -> {out_wav}")
        with VideoFileClip(video_path) as clip:
            if clip.audio is None:
                raise RuntimeError("Source video has no audio track")
            clip.audio.write_audiofile(out_wav, logger=None)
        return out_wav

    # ---------- Step 3: transcribe ----------

    def transcribe_with_timestamps(self, audio_path: str) -> List[dict]:
        """Whisper transcription returning structured segments with timestamps."""
        provider = (get_stt_provider() or "local_whisper").strip().lower()
        if provider != "local_whisper":
            warning(
                f"STT provider '{provider}' is not supported for movie summaries; "
                f"falling back to local Whisper."
            )

        from faster_whisper import WhisperModel

        model_size = get_whisper_model() or "base"
        device = get_whisper_device() or "auto"
        compute_type = get_whisper_compute_type() or "int8"

        info(f"[Movie] Whisper transcribe (model={model_size}, device={device})")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments_iter, _info = model.transcribe(audio_path, vad_filter=True)
        segments = [
            {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments_iter
            if (s.text or "").strip()
        ]
        success(f"[Movie] {len(segments)} transcript segments")
        return segments

    # ---------- Step 4: chunking ----------

    def _chunk_transcript(self, segments: List[dict], max_minutes: int) -> List[List[dict]]:
        """Split segments into <= max_minutes windows on segment boundaries."""
        if not segments:
            return []
        window = max_minutes * 60.0
        chunks: List[List[dict]] = []
        current: List[dict] = []
        chunk_start = segments[0]["start"]
        for seg in segments:
            if seg["start"] - chunk_start > window and current:
                chunks.append(current)
                current = []
                chunk_start = seg["start"]
            current.append(seg)
        if current:
            chunks.append(current)
        return chunks

    # ---------- Step 5: extract emotional beats (Stage 1) ----------

    def extract_beats(self, chunks: List[List[dict]]) -> List[dict]:
        """One LLM call per transcript chunk. Returns merged, time-sorted beats."""
        if not chunks:
            return []

        all_beats: List[dict] = []
        long_model = get_long_video_llm_model()

        for idx, chunk in enumerate(chunks, start=1):
            info(f"[Movie] Stage 1/2 — beat extraction chunk {idx}/{len(chunks)}")
            transcript_text = "\n".join(
                f"[{self._fmt_ts(s['start'])}-{self._fmt_ts(s['end'])}] {s['text']}"
                for s in chunk
            )
            prompt = (
                f"Eres un analista de cine. Lee este fragmento {idx} de {len(chunks)} "
                f"de la transcripción de una película (con timestamps en segundos) "
                f"y devuelve SOLO JSON con los momentos importantes.\n\n"
                f"Esquema EXACTO:\n"
                f'{{"beats": [{{"t": 1234.5, "type": "setup|plot_twist|death|reveal|climax|resolution", "importance": 1, "summary": "..."}}]}}\n\n'
                f"Reglas:\n"
                f"- 'importance' va de 1 a 10. 10 = clímax, 9 = giro/muerte principal, 7-8 = revelación, 4-6 = setup/transición.\n"
                f"- Mínimo 4 beats por fragmento si su duración lo permite.\n"
                f"- 't' SIEMPRE en segundos (float), dentro del rango de timestamps que ves abajo.\n"
                f"- 'summary' en español, 1-2 frases, describe qué pasa en ese punto.\n"
                f"- NUNCA inventes timestamps fuera del rango.\n\n"
                f"TRANSCRIPCIÓN:\n{transcript_text}\n\n"
                f"Devuelve SOLO el JSON, sin markdown, sin explicación."
            )
            with force_provider("ollama", long_model, think="medium"):
                raw = generate_text(prompt)
            parsed = self._parse_json_object(raw)
            beats = parsed.get("beats", []) if isinstance(parsed, dict) else []
            chunk_lo = chunk[0]["start"]
            chunk_hi = chunk[-1]["end"]
            for b in beats:
                try:
                    t = float(b.get("t", 0))
                except (TypeError, ValueError):
                    continue
                if t < chunk_lo - 5 or t > chunk_hi + 5:
                    # Hallucinated — skip
                    continue
                btype = str(b.get("type", "")).strip().lower()
                if btype not in ALL_BEAT_TYPES:
                    continue
                try:
                    importance = int(b.get("importance", 5))
                except (TypeError, ValueError):
                    importance = 5
                importance = max(1, min(10, importance))
                summary = str(b.get("summary", "")).strip()
                all_beats.append(
                    {
                        "t": t,
                        "type": btype,
                        "importance": importance,
                        "summary": summary,
                    }
                )

        all_beats.sort(key=lambda b: b["t"])
        info(f"[Movie] Stage 1 complete — {len(all_beats)} merged beats")
        return all_beats

    # ---------- Step 6: plan the video (Stage 2) ----------

    def plan_video(
        self,
        beats: List[dict],
        runtime: float,
        language: str,
        segments: List[dict],
        retry_reason: Optional[str] = None,
    ) -> dict:
        """Single LLM call given the merged beats. Returns the plan dict."""
        long_model = get_long_video_llm_model()
        max_total = get_movie_max_duration_seconds()
        hook_seconds = get_movie_hook_seconds()
        min_clip = get_movie_min_clip_seconds()
        max_clip = get_movie_max_clip_seconds()
        body_budget = max_total - hook_seconds

        beats_text = "\n".join(
            f"- t={b['t']:.1f}s | {b['type']} (importance {b['importance']}) | {b['summary']}"
            for b in beats
        )

        retry_block = ""
        if retry_reason:
            retry_block = (
                f"\nIMPORTANTE: el intento anterior falló validación: {retry_reason}\n"
                f"Corrige y NO repitas el error.\n"
            )

        prompt = (
            f"Eres un guionista de canales de resúmenes de películas en {language}. "
            f"Optimizas retención y CTR. Devuelves SOLO JSON válido.{retry_block}\n\n"
            f"Película: duración total = {runtime:.0f} segundos.\n"
            f"Lista de beats detectados (timestamps en segundos):\n{beats_text}\n\n"
            f"Genera un plan de resumen con:\n"
            f"1) hook: una frase de unos {hook_seconds}s que enganche al espectador. "
            f"PROHIBIDO mencionar el final, identidad del villano, quién muere, "
            f"reveals o clímax. Solo setup, atmósfera y la pregunta central.\n"
            f"2) clips: lista de cortes en orden cronológico (start/end en segundos del video original), "
            f"cada uno entre {min_clip} y {max_clip} segundos. La suma de duraciones <= {body_budget}s. "
            f"DEBE incluir el clímax y al menos uno de tipo plot_twist, death o reveal.\n"
            f"3) thumbnail_timestamp: segundo del frame más emotivo (importance >= 8) "
            f"en los primeros 85% del video.\n"
            f"4) thumbnail_overlay: frase clickbait corta en MAYÚSCULAS (3-6 palabras).\n\n"
            f"Esquema EXACTO:\n"
            f'{{\n'
            f'  "hook": {{"narration": "...", "duration": {hook_seconds}}},\n'
            f'  "clips": [\n'
            f'    {{"start": 12.5, "end": 38.0, "beat_type": "setup", "importance": 5, "narration": "..."}}\n'
            f'  ],\n'
            f'  "thumbnail_timestamp": 1247.0,\n'
            f'  "thumbnail_overlay": "FRASE CORTA"\n'
            f'}}\n\n'
            f"Toda la narración en {language}. Devuelve SOLO el JSON."
        )

        with force_provider("ollama", long_model, think="high"):
            raw = generate_text(prompt)
        parsed = self._parse_json_object(raw)
        if not isinstance(parsed, dict):
            raise PlanValidationError("LLM did not return a JSON object")
        return parsed

    # ---------- Step 7: validate the plan (anti-hallucination) ----------

    def validate_plan(
        self,
        plan: dict,
        runtime: float,
        segments: List[dict],
    ) -> dict:
        """
        Strict timestamp + structure validation. Snaps near-misses, drops
        impossible entries, raises PlanValidationError on hard failures.
        """
        max_total = get_movie_max_duration_seconds()
        hook_seconds = get_movie_hook_seconds()
        min_clip = get_movie_min_clip_seconds()
        max_clip = get_movie_max_clip_seconds()
        body_budget = max_total - hook_seconds

        # Clamp to runtime. We deliberately do NOT require the timestamp to be
        # inside a Whisper-detected speech segment — documentaries, archival
        # footage, action sequences and silent films all have visually
        # important moments without spoken dialogue. The LLM hallucination we
        # actually need to defend against is a t-value way out of bounds
        # (e.g. t=8421s when runtime=5489s), which the runtime clamp handles.
        def _validate_ts(t: float) -> float:
            return max(0.0, min(float(t), runtime - 0.5))

        # ----- Hook -----
        hook = plan.get("hook") or {}
        hook_narration = str(hook.get("narration", "")).strip()
        if not hook_narration:
            raise PlanValidationError("hook.narration empty")

        # ----- Clips -----
        raw_clips = plan.get("clips") or []
        if not isinstance(raw_clips, list) or not raw_clips:
            raise PlanValidationError("clips list empty")

        clips = []
        prev_end = -1.0
        for i, c in enumerate(raw_clips):
            try:
                start = float(c.get("start"))
                end = float(c.get("end"))
            except (TypeError, ValueError):
                raise PlanValidationError(f"clip {i} has non-numeric start/end")
            start = _validate_ts(start)
            end = _validate_ts(end)
            if end <= start:
                raise PlanValidationError(f"clip {i} end {end:.1f} <= start {start:.1f}")
            duration = end - start
            if duration < min_clip:
                # Stretch end to min_clip if there's room
                end = min(start + min_clip, runtime - 0.5)
                duration = end - start
                if duration < min_clip * 0.6:
                    raise PlanValidationError(
                        f"clip {i} too short ({duration:.1f}s)"
                    )
            if duration > max_clip:
                end = start + max_clip
                duration = end - start
            if start < prev_end:
                raise PlanValidationError(
                    f"clip {i} starts before previous end ({start:.1f} < {prev_end:.1f})"
                )
            beat_type = str(c.get("beat_type", "")).strip().lower() or "setup"
            if beat_type not in ALL_BEAT_TYPES:
                beat_type = "setup"
            try:
                importance = int(c.get("importance", 5))
            except (TypeError, ValueError):
                importance = 5
            importance = max(1, min(10, importance))
            narration = str(c.get("narration", "")).strip()
            if not narration:
                raise PlanValidationError(f"clip {i} has empty narration")
            clips.append(
                {
                    "start": start,
                    "end": end,
                    "duration": duration,
                    "beat_type": beat_type,
                    "importance": importance,
                    "narration": narration,
                }
            )
            prev_end = end

        # Required beat types
        types_present = {c["beat_type"] for c in clips}
        if "climax" not in types_present:
            raise PlanValidationError("plan is missing the climax beat")
        if not (types_present & {"plot_twist", "death", "reveal"}):
            raise PlanValidationError(
                "plan must include at least one of plot_twist / death / reveal"
            )

        # Trim trailing low-importance clips until total fits
        total = sum(c["duration"] for c in clips)
        if total > body_budget:
            ordered_for_trim = sorted(
                range(len(clips)),
                key=lambda i: (clips[i]["importance"], -i),
            )
            climax_idx = next(
                i for i, c in enumerate(clips) if c["beat_type"] == "climax"
            )
            kept_mask = [True] * len(clips)
            for i in ordered_for_trim:
                if total <= body_budget:
                    break
                if i == climax_idx:
                    continue
                kept_mask[i] = False
                total -= clips[i]["duration"]
            clips = [c for c, keep in zip(clips, kept_mask) if keep]
            if total > body_budget:
                raise PlanValidationError(
                    f"could not fit clips into budget ({total:.1f}s > {body_budget}s)"
                )

        # ----- Thumbnail timestamp -----
        try:
            tn_ts = float(plan.get("thumbnail_timestamp", 0))
        except (TypeError, ValueError):
            tn_ts = 0.0
        tn_ts = _validate_ts(tn_ts)
        if tn_ts > runtime * 0.85:
            # Pick the highest-importance non-climax beat in first 85%
            cap = runtime * 0.85
            candidates = [c for c in clips if c["start"] < cap and c["beat_type"] != "climax"]
            if candidates:
                pick = max(candidates, key=lambda c: c["importance"])
                tn_ts = (pick["start"] + pick["end"]) / 2
            else:
                tn_ts = clips[0]["start"]

        thumbnail_overlay = str(plan.get("thumbnail_overlay", "")).strip().upper()

        return {
            "hook": {"narration": hook_narration, "duration": float(hook.get("duration", get_movie_hook_seconds()))},
            "clips": clips,
            "thumbnail_timestamp": tn_ts,
            "thumbnail_overlay": thumbnail_overlay,
        }

    # ---------- Deterministic fallback ----------

    def _fallback_plan(self, beats: List[dict], runtime: float) -> dict:
        """Build a plan directly from beats when the LLM fails twice."""
        warning("[Movie] Falling back to deterministic plan from beats")
        max_total = get_movie_max_duration_seconds()
        hook_seconds = get_movie_hook_seconds()
        min_clip = get_movie_min_clip_seconds()
        body_budget = max_total - hook_seconds

        # Force a climax pick if any
        climax_beats = [b for b in beats if b["type"] == "climax"]
        twist_beats = [b for b in beats if b["type"] in {"plot_twist", "death", "reveal"}]
        other_beats = [b for b in beats if b["type"] not in {"climax", "plot_twist", "death", "reveal"}]

        chosen: List[dict] = []
        chosen.extend(sorted(climax_beats, key=lambda b: -b["importance"])[:1])
        chosen.extend(sorted(twist_beats, key=lambda b: -b["importance"])[: max(1, body_budget // 60)])
        chosen.extend(sorted(other_beats, key=lambda b: -b["importance"])[: max(2, body_budget // 90)])
        chosen.sort(key=lambda b: b["t"])

        clip_len = max(min_clip, 25)
        clips = []
        for b in chosen:
            start = max(0.0, b["t"] - clip_len / 2)
            end = min(runtime - 0.5, start + clip_len)
            clips.append(
                {
                    "start": start,
                    "end": end,
                    "beat_type": b["type"],
                    "importance": b["importance"],
                    "narration": b["summary"] or f"En este momento, {b['type']}.",
                }
            )

        # Pick a thumbnail beat in the first 85%
        cap = runtime * 0.85
        tn_candidates = [b for b in beats if b["t"] < cap and b["type"] != "climax"]
        tn_ts = (
            max(tn_candidates, key=lambda b: b["importance"])["t"]
            if tn_candidates
            else (clips[0]["start"] if clips else 0.0)
        )

        return {
            "hook": {
                "narration": "Esta historia esconde un secreto que cambiará todo lo que crees saber.",
                "duration": hook_seconds,
            },
            "clips": clips,
            "thumbnail_timestamp": tn_ts,
            "thumbnail_overlay": "NO TE LO PIERDAS",
        }

    # ---------- Step 8: thumbnail frame extraction ----------

    def extract_thumbnail_frame(self, video_path: str, timestamp: float) -> str:
        """ffmpeg-extract a single frame, retrying nearby if the frame is near-black."""
        from PIL import Image
        from compat import find_ffmpeg
        ffmpeg = find_ffmpeg() or "ffmpeg"
        attempts = [0.0, 2.0, -2.0, 4.0]
        for delta in attempts:
            ts = max(0.5, timestamp + delta)
            out = os.path.join(ROOT_DIR, ".mp", f"thumb_{uuid4()}.png")
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-ss",
                        f"{ts:.2f}",
                        "-i",
                        video_path,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        out,
                    ],
                    capture_output=True,
                    timeout=60,
                )
            except Exception as e:
                warning(f"[Movie] ffmpeg frame extract at {ts:.1f}s failed: {e}")
                continue
            if not os.path.isfile(out) or os.path.getsize(out) < 5000:
                continue
            try:
                img = Image.open(out).convert("L")
                pixels = list(img.getdata())
                mean_luma = sum(pixels) / max(1, len(pixels))
                if mean_luma >= 15:
                    return out
                if get_verbose():
                    info(f"[Movie] Frame at {ts:.1f}s too dark (luma {mean_luma:.1f}), retrying")
                os.remove(out)
            except Exception:
                return out
        raise RuntimeError("Could not extract a usable thumbnail frame")

    # ---------- Override thumbnail bg loader ----------

    def _try_nanobanana2_landscape(self, prompt: str) -> Optional[bytes]:
        """Override: feed the inherited generate_thumbnail() the extracted frame."""
        path = getattr(self, "_thumbnail_base_path", "")
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()
        return super()._try_nanobanana2_landscape(prompt)

    # ---------- Step 9: hook clip ----------

    def _build_hook_clip(
        self,
        source_path: str,
        plan: dict,
        beats: List[dict],
        runtime: float,
        tts_instance: TTS,
    ):
        """
        Build a 15s opening hook from beats that are SAFE to show:
          - t < 0.6 * runtime
          - type NOT IN {climax, resolution}
          - if death: not in last 25% AND importance < 9 (final death is reserved for body)
        """
        hook_seconds = get_movie_hook_seconds()
        narration_text = plan["hook"]["narration"]

        late_cutoff = runtime * 0.6
        death_cutoff = runtime * 0.75
        candidates = []
        for b in beats:
            if b["t"] >= late_cutoff:
                continue
            if b["type"] in HOOK_FORBIDDEN_BEAT_TYPES:
                continue
            if b["type"] == "death" and (b["t"] >= death_cutoff or b["importance"] >= 9):
                continue
            candidates.append(b)

        candidates.sort(key=lambda b: -b["importance"])

        # Render hook narration first so we know the audio length
        hook_audio_path = os.path.join(ROOT_DIR, ".mp", f"hook_{uuid4()}.wav")
        voice = self._resolve_voice(self._long_voice) or LONG_VIDEO_NARRATOR
        tts_instance.synthesize_long(narration_text, hook_audio_path, voice_id=voice)
        narration = AudioFileClip(hook_audio_path)
        target_duration = max(hook_seconds, narration.duration)

        # Pick 3 short ranges around the top candidates; default to first 15s if empty
        ranges = []
        per_clip = max(3.5, target_duration / 3.0)
        used_starts = set()
        for b in candidates:
            if len(ranges) >= 3:
                break
            start = max(0.5, b["t"] - per_clip / 2)
            end = min(runtime - 0.5, start + per_clip)
            # avoid near-duplicates
            if any(abs(start - u) < 4.0 for u in used_starts):
                continue
            used_starts.add(start)
            ranges.append((start, end))

        if not ranges:
            ranges = [(0.5, min(runtime - 0.5, 15.0))]

        ranges.sort(key=lambda r: r[0])

        sub_clips = []
        for start, end in ranges:
            sc = VideoFileClip(source_path).subclip(start, end).without_audio()
            sub_clips.append(sc)

        visuals = concatenate_videoclips(sub_clips, method="compose")

        # Trim or extend visuals to match narration duration
        if visuals.duration > target_duration:
            visuals = visuals.subclip(0, target_duration)
        elif visuals.duration < target_duration:
            last_frame = visuals.get_frame(visuals.duration - 0.05)
            extra = ImageClip(last_frame).set_duration(target_duration - visuals.duration).set_fps(30)
            visuals = concatenate_videoclips([visuals, extra], method="compose")

        # 8% original audio bed under TTS
        original_audio_clips = []
        for start, end in ranges:
            try:
                src_aud = VideoFileClip(source_path).subclip(start, end).audio
                if src_aud is not None:
                    original_audio_clips.append(src_aud.volumex(get_movie_original_audio_volume()))
            except Exception:
                continue

        if original_audio_clips:
            from moviepy.audio.AudioClip import concatenate_audioclips
            bed = concatenate_audioclips(original_audio_clips)
            if bed.duration > target_duration:
                bed = bed.subclip(0, target_duration)
            mixed = CompositeAudioClip([bed, narration.volumex(1.0)])
        else:
            mixed = narration.volumex(1.0)

        return visuals.set_audio(mixed)

    # ---------- Step 10: cut & narrate body ----------

    def cut_and_narrate(self, plan: dict, source_path: str, tts_instance: TTS, runtime: float):
        """Build hook + body clips, write final MP4. Returns the path."""
        hook_clip = self._build_hook_clip(
            source_path, plan, plan.get("_beats_for_hook", []), runtime, tts_instance
        )

        voice = self._resolve_voice(self._long_voice) or LONG_VIDEO_NARRATOR

        body_clips = []
        for i, c in enumerate(plan["clips"]):
            info(f"[Movie] Body clip {i + 1}/{len(plan['clips'])} "
                 f"({c['start']:.1f}-{c['end']:.1f}s, {c['beat_type']})")

            # Visual + original audio
            base = VideoFileClip(source_path).subclip(c["start"], c["end"])

            # TTS narration
            narration_path = os.path.join(ROOT_DIR, ".mp", f"narr_{uuid4()}.wav")
            tts_instance.synthesize_long(c["narration"], narration_path, voice_id=voice)
            narration = AudioFileClip(narration_path)

            # Fit visual to narration
            if narration.duration > base.duration:
                delta = narration.duration - base.duration
                last_frame = base.get_frame(base.duration - 0.05)
                tail = ImageClip(last_frame).set_duration(delta).set_fps(base.fps or 30)
                visual = concatenate_videoclips([base.without_audio(), tail], method="compose")
                src_audio_for_mix = base.audio
            else:
                visual = base.without_audio()
                if narration.duration < base.duration:
                    visual = visual.subclip(0, narration.duration)
                src_audio_for_mix = base.audio.subclip(0, narration.duration) if base.audio else None

            if src_audio_for_mix is not None:
                bed = src_audio_for_mix.volumex(get_movie_original_audio_volume())
                # Make sure bed isn't longer than visual after potential freeze-extend
                if bed.duration > visual.duration:
                    bed = bed.subclip(0, visual.duration)
                mixed = CompositeAudioClip([bed, narration.volumex(1.0)])
            else:
                mixed = narration.volumex(1.0)

            body_clips.append(visual.set_audio(mixed))

        all_clips = [hook_clip] + body_clips
        final = concatenate_videoclips(all_clips, method="compose", padding=-0.6)

        out_path = os.path.join(ROOT_DIR, ".mp", f"{uuid4()}.mp4")
        info(f"[Movie] Writing final video -> {out_path}")
        final.write_videofile(
            out_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=get_threads(),
            preset="medium",
            logger="bar",
        )
        return out_path

    # ---------- Public entry point ----------

    def generate_movie_summary(
        self,
        tts_instance: TTS,
        movie_title: str,
        archive_identifier: Optional[str] = None,
    ) -> str:
        """
        End-to-end: download → transcribe → plan → assemble → upload-ready MP4.
        If `archive_identifier` is given, downloads from archive.org instead of
        searching YouTube.
        Returns the final video path.
        """
        info("=" * 50)
        info(f"  MOVIE SUMMARY PIPELINE: {movie_title}")
        info("=" * 50)

        if not movie_title or not movie_title.strip():
            error("No movie title provided; aborting.")
            self.video_path = ""
            return ""

        self.subject = movie_title.strip()
        self._is_long_video = True
        self.active_series = None
        self._archive_identifier = archive_identifier or ""

        long_model = get_long_video_llm_model()
        info(f"  Long-video LLM: ollama/{long_model}")
        warmup_ollama_model(long_model)

        # Step 1: download
        info("\n[1/8] Downloading movie...")
        source_path = self.download_movie(self.subject, archive_identifier=archive_identifier)

        # Step 2: extract audio
        info("\n[2/8] Extracting audio...")
        audio_path = self.extract_audio(source_path)
        runtime = AudioFileClip(audio_path).duration
        info(f" => Runtime: {runtime:.0f}s ({runtime/60:.1f} min)")

        # Step 3: transcribe
        info("\n[3/8] Transcribing...")
        segments = self.transcribe_with_timestamps(audio_path)
        if not segments:
            error("No transcript segments produced; aborting.")
            self.video_path = ""
            return ""

        # Step 4: chunk + Stage-1 beat extraction
        info("\n[4/8] Extracting beats (Stage 1)...")
        chunks = self._chunk_transcript(segments, get_movie_chunk_minutes())
        beats = self.extract_beats(chunks)
        if not beats:
            warning("No beats extracted; falling back will use empty list.")

        # Step 5: Stage-2 plan with one retry on validation failure
        info("\n[5/8] Building plan (Stage 2)...")
        validated_plan = None
        retry_reason = None
        for attempt in (1, 2):
            try:
                raw_plan = self.plan_video(
                    beats, runtime, self.language or "Spanish", segments, retry_reason
                )
                validated_plan = self.validate_plan(raw_plan, runtime, segments)
                break
            except PlanValidationError as e:
                warning(f"[Movie] Plan validation failed (attempt {attempt}): {e}")
                retry_reason = str(e)
            except Exception as e:
                warning(f"[Movie] Plan call failed (attempt {attempt}): {e}")
                retry_reason = f"exception: {e}"

        if validated_plan is None:
            validated_plan = self._fallback_plan(beats, runtime)
            # Re-validate the fallback so downstream code can trust it
            try:
                validated_plan = self.validate_plan(validated_plan, runtime, segments)
            except PlanValidationError as e:
                error(f"[Movie] Even fallback plan failed validation: {e}")
                self.video_path = ""
                return ""

        validated_plan["_beats_for_hook"] = beats

        # Step 6: thumbnail frame
        info("\n[6/8] Extracting thumbnail frame...")
        try:
            tn_path = self.extract_thumbnail_frame(
                source_path, validated_plan["thumbnail_timestamp"]
            )
            self._thumbnail_base_path = tn_path
        except Exception as e:
            warning(f"[Movie] Thumbnail frame extraction failed: {e}")
            self._thumbnail_base_path = ""

        # Step 7: synthesize a script for metadata + run inherited metadata/thumbnail
        info("\n[7/8] Generating metadata + thumbnail...")
        narrations = [validated_plan["hook"]["narration"]] + [
            c["narration"] for c in validated_plan["clips"]
        ]
        self.script = "\n\n".join(narrations)
        self.metadata = self.generate_long_metadata()
        success(f" Title: {self.metadata.get('title', '')}")

        try:
            self.generate_thumbnail()
        except Exception as e:
            warning(f"[Movie] Thumbnail generation failed: {e}")
            self.thumbnail_path = ""

        # Step 8: cut & narrate
        info("\n[8/8] Cutting clips and narrating...")
        final_path = self.cut_and_narrate(validated_plan, source_path, tts_instance, runtime)
        self.video_path = os.path.abspath(final_path)
        self._save_metadata_sidecar()

        # Cleanup heavy intermediates
        for p in (source_path, audio_path):
            try:
                if p and os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass

        # Persist to the per-account summarized list so the catalog browser
        # can mark this movie as already done.
        if archive_identifier:
            try:
                self._record_summarized(archive_identifier, movie_title)
            except Exception as e:
                warning(f"[Movie] Could not persist summarized record: {e}")

        success(f"\n=> Movie summary generated: {final_path}")
        return final_path

    def _record_summarized(self, identifier: str, title: str) -> None:
        """
        Append {identifier, title, date} to account[summarized_movies] in
        .mp/movies.json so the catalog browser knows what's already done.
        """
        from datetime import datetime

        cache_path = os.path.join(ROOT_DIR, ".mp", "movies.json")
        if not os.path.isfile(cache_path):
            return
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for acc in data.get("accounts", []):
            if acc.get("id") == self._account_uuid:
                lst = acc.setdefault("summarized_movies", [])
                if not any(e.get("identifier") == identifier for e in lst):
                    lst.append(
                        {
                            "identifier": identifier,
                            "title": title,
                            "date": datetime.utcnow().strftime("%Y-%m-%d"),
                        }
                    )
                break
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ---------- helpers ----------

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _parse_json_object(raw: str) -> dict:
        """Parse a JSON object out of an LLM response, stripping markdown fences."""
        if raw is None:
            return {}
        text = str(raw).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                return {}
            try:
                return json.loads(m.group())
            except Exception:
                return {}
