from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cache import get_temp_cache_path
from utils import (
    clean_script_for_tts,
    expand_regnal_numerals,
    expand_regnal_numerals_tracked,
    expand_spanish_numbers,
    expand_spoken_symbols,
    restore_regnal_numerals_in_timestamps,
    strip_stage_directions,
)

from .MaxRetention import MaxRetentionEngine, is_max_retention, normalize_retention_mode
from .Tts import EDGE_TTS_VOICES, LONG_VIDEO_NARRATOR, TTS


@dataclass(frozen=True)
class ScriptVoicePreviewConfig:
    language: str = "espanol"
    short_voice: str = ""
    long_voice: str = ""
    voice_drama: bool = False
    retention_mode: str = ""


@dataclass(frozen=True)
class ScriptVoicePreviewResult:
    audio_path: str
    sidecar_path: str
    subject: str
    script: str
    tts_text: str
    duration_seconds: float
    word_count: int
    kind: str
    voice_id: str
    word_timestamps: list[dict] | None = None

    def to_dict(self) -> dict:
        return {
            "audio_path": self.audio_path,
            "sidecar_path": self.sidecar_path,
            "subject": self.subject,
            "script": self.script,
            "tts_text": self.tts_text,
            "duration_seconds": self.duration_seconds,
            "word_count": self.word_count,
            "kind": self.kind,
            "voice_id": self.voice_id,
            "word_timestamps": self.word_timestamps,
        }


class ScriptVoicePreview:
    """Generate a voice-only preview from an approved video script.

    This intentionally does not instantiate YouTube or touch Firefox. It mirrors
    the same TTS cleaning, voice selection, and retention-rate settings used by
    the full render flow, then emits a standalone WAV for quick listening.
    """

    def __init__(
        self,
        config: ScriptVoicePreviewConfig | None = None,
        tts_instance: TTS | None = None,
        output_dir: str | os.PathLike | None = None,
    ) -> None:
        self.config = config or ScriptVoicePreviewConfig()
        self.tts_instance = tts_instance or TTS()
        self.output_dir = Path(output_dir or get_temp_cache_path())
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_channel(
        cls,
        channel: dict,
        *,
        retention_mode: str = "",
        tts_instance: TTS | None = None,
        output_dir: str | os.PathLike | None = None,
    ) -> "ScriptVoicePreview":
        config = ScriptVoicePreviewConfig(
            language=str(channel.get("language", "") or "espanol"),
            short_voice=str(channel.get("short_voice", "") or ""),
            long_voice=str(channel.get("long_voice", "") or ""),
            voice_drama=bool(channel.get("voice_drama", False)),
            retention_mode=normalize_retention_mode(retention_mode or ""),
        )
        return cls(config=config, tts_instance=tts_instance, output_dir=output_dir)

    def synthesize(
        self,
        *,
        subject: str,
        script: str,
        kind: str = "short",
        preview_id: str = "",
    ) -> ScriptVoicePreviewResult:
        kind = (kind or "short").strip().lower()
        if kind not in {"short", "long"}:
            raise ValueError("kind must be 'short' or 'long'")

        subject = (subject or "").strip()
        script = (script or "").strip()
        if not script:
            raise ValueError("script is required")

        key = _safe_artifact_key(preview_id or uuid4().hex)
        audio_path = self.output_dir / f".preview-voice-{key}.wav"
        sidecar_path = self.output_dir / f".preview-voice-{key}.json"

        if kind == "long":
            result = self._synthesize_long(subject, script, audio_path)
        else:
            result = self._synthesize_short(subject, script, audio_path)

        final = ScriptVoicePreviewResult(
            audio_path=str(audio_path),
            sidecar_path=str(sidecar_path),
            subject=subject,
            script=script,
            tts_text=result["tts_text"],
            duration_seconds=_audio_duration_seconds(audio_path),
            word_count=_word_count(result["tts_text"]),
            kind=kind,
            voice_id=result["voice_id"],
            word_timestamps=result.get("word_timestamps"),
        )
        sidecar_path.write_text(
            json.dumps(final.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return final

    def _synthesize_short(self, subject: str, script: str, audio_path: Path) -> dict:
        spoken_script = strip_stage_directions(script)
        spoken_script = clean_script_for_tts(spoken_script)
        tts_text, regnal_subs = expand_regnal_numerals_tracked(spoken_script)
        tts_text = expand_spanish_numbers(tts_text)

        voice_id = _resolve_voice(self.config.short_voice)
        if is_max_retention(self.config.retention_mode):
            rate = MaxRetentionEngine.VOICE_RATE
            pitch = MaxRetentionEngine.VOICE_DRAMA_PITCH if self.config.voice_drama else ""
        else:
            rate = "-5%" if self.config.voice_drama else ""
            pitch = "-8Hz" if self.config.voice_drama else ""

        _, word_timestamps = self.tts_instance.synthesize_with_timestamps(
            tts_text,
            str(audio_path),
            voice_id=voice_id or None,
            rate=rate,
            pitch=pitch,
        )
        if word_timestamps:
            word_timestamps = restore_regnal_numerals_in_timestamps(
                word_timestamps,
                regnal_subs,
            )

        return {
            "subject": subject,
            "tts_text": tts_text,
            "voice_id": voice_id,
            "word_timestamps": word_timestamps,
        }

    def _synthesize_long(self, subject: str, script: str, audio_path: Path) -> dict:
        tts_text = _clean_long_script_for_tts(script)
        if not tts_text or len(tts_text.split()) < 50:
            tts_text = re.sub(r"\[.*?\]", "", script).strip()

        tts_text = expand_spoken_symbols(tts_text)
        tts_text = expand_regnal_numerals(tts_text)
        tts_text = expand_spanish_numbers(tts_text)

        voice_id = _resolve_voice(self.config.long_voice) or LONG_VIDEO_NARRATOR
        if _is_spanish_language(self.config.language) and not voice_id.lower().startswith("es-"):
            voice_id = LONG_VIDEO_NARRATOR

        self.tts_instance.synthesize_long(tts_text, str(audio_path), voice_id=voice_id)
        return {
            "subject": subject,
            "tts_text": tts_text,
            "voice_id": voice_id,
            "word_timestamps": None,
        }


def _resolve_voice(voice: str) -> str:
    voice = (voice or "").strip()
    if not voice:
        return ""
    return EDGE_TTS_VOICES.get(voice, voice)


def _safe_artifact_key(value: str) -> str:
    value = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", value):
        return uuid4().hex
    return value


def _is_spanish_language(language: str) -> bool:
    lang = (language or "").strip().lower()
    return lang.startswith("esp") or lang in {"es", "spanish", "espanol"}


def _clean_long_script_for_tts(script: str) -> str:
    text = strip_stage_directions(script or "")
    text = re.sub(
        r"\[(INTRO|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\[(SECTION|SECCION)\s*\d+\s*:?[^\]]*\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^\s*(INTRO|INTRODUCCION|CLOSING|CIERRE|OUTRO|DESPEDIDA)\s*:?\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"^\s*(SECTION|SECCION)\s*\d+\s*:[^\n]*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(r'"role"\s*:\s*"[^"]*"', "", text)
    text = re.sub(r'"content"\s*:\s*"', "", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bwww\.\S+", "", text)
    text = re.sub(
        r"\b[\w.-]+\.(?:com|org|net|io|ai|gov|edu|co|es|app|dev|tv)(?:/\S*)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"^\s*[\{\}]\s*", "", text)
    text = re.sub(r"\s*[\{\}]\s*$", "", text)
    text = re.sub(r"\b\w+(?:[_-]\w+){1,}\b", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _audio_duration_seconds(audio_path: Path) -> float:
    if not audio_path.is_file() or audio_path.stat().st_size <= 0:
        return 0.0
    try:
        from moviepy.editor import AudioFileClip

        clip = AudioFileClip(str(audio_path))
        try:
            return float(clip.duration or 0.0)
        finally:
            clip.close()
    except Exception:
        return 0.0


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or "", flags=re.UNICODE))
