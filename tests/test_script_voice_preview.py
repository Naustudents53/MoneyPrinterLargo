import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.MaxRetention import MaxRetentionEngine
from classes.ScriptVoicePreview import (
    ScriptVoicePreview,
    ScriptVoicePreviewConfig,
)
from classes.Tts import LONG_VIDEO_NARRATOR


class FakeTTS:
    def __init__(self):
        self.short_calls = []
        self.long_calls = []

    def synthesize_with_timestamps(self, text, output_file, voice_id=None, rate="", pitch=""):
        Path(output_file).write_bytes(b"fake audio")
        self.short_calls.append({
            "text": text,
            "output_file": output_file,
            "voice_id": voice_id,
            "rate": rate,
            "pitch": pitch,
        })
        return output_file, [{"start": 0.0, "end": 0.2, "word": "primero"}]

    def synthesize_long(self, text, output_file, voice_id=None):
        Path(output_file).write_bytes(b"fake audio")
        self.long_calls.append({
            "text": text,
            "output_file": output_file,
            "voice_id": voice_id,
        })
        return output_file


def test_short_voice_preview_uses_same_retention_voice_settings(tmp_path):
    fake_tts = FakeTTS()
    preview = ScriptVoicePreview(
        config=ScriptVoicePreviewConfig(
            language="espanol",
            short_voice="Pablo",
            voice_drama=True,
            retention_mode="maxima_retencion",
        ),
        tts_instance=fake_tts,
        output_dir=tmp_path,
    )

    result = preview.synthesize(
        subject="Cosimo I",
        script="Cosimo I vio el 90% del mapa en 1453.",
        preview_id="abc123",
    )

    assert Path(result.audio_path).is_file()
    assert Path(result.sidecar_path).is_file()
    assert result.kind == "short"
    assert result.voice_id == "es-ES-AlvaroNeural"
    assert result.word_timestamps == [{"start": 0.0, "end": 0.2, "word": "I"}]

    call = fake_tts.short_calls[0]
    assert call["voice_id"] == "es-ES-AlvaroNeural"
    assert call["rate"] == MaxRetentionEngine.VOICE_RATE
    assert call["pitch"] == MaxRetentionEngine.VOICE_DRAMA_PITCH
    assert "por ciento" in call["text"]
    assert "primero" in call["text"]

    sidecar = json.loads(Path(result.sidecar_path).read_text(encoding="utf-8"))
    assert sidecar["audio_path"] == result.audio_path
    assert sidecar["word_count"] == result.word_count


def test_short_voice_preview_falls_back_to_spanish_narrator(tmp_path, monkeypatch):
    monkeypatch.setattr("classes.ScriptVoicePreview.get_tts_voice", lambda: "Jasper")
    fake_tts = FakeTTS()
    preview = ScriptVoicePreview(
        config=ScriptVoicePreviewConfig(language="espanol"),
        tts_instance=fake_tts,
        output_dir=tmp_path,
    )

    result = preview.synthesize(
        subject="Short test",
        script="Este planeta tiene vientos imposibles.",
        preview_id="shortspanish",
    )

    assert result.voice_id == LONG_VIDEO_NARRATOR
    assert fake_tts.short_calls[0]["voice_id"] == LONG_VIDEO_NARRATOR


def test_long_voice_preview_falls_back_to_spanish_narrator(tmp_path):
    fake_tts = FakeTTS()
    preview = ScriptVoicePreview(
        config=ScriptVoicePreviewConfig(
            language="espanol",
            long_voice="Bruno",
        ),
        tts_instance=fake_tts,
        output_dir=tmp_path,
    )
    script = "En 1453 paso algo que cambio el mundo. " * 55

    result = preview.synthesize(
        subject="Long test",
        script=script,
        kind="long",
        preview_id="long123",
    )

    assert Path(result.audio_path).is_file()
    assert result.kind == "long"
    assert result.voice_id == LONG_VIDEO_NARRATOR
    assert fake_tts.long_calls[0]["voice_id"] == LONG_VIDEO_NARRATOR
    assert "mil cuatrocientos" in fake_tts.long_calls[0]["text"]
