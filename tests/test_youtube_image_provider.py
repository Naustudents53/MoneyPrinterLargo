import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import codex_image_provider
import llm_provider
from classes.YouTube import YouTube


def test_codex_image_provider_does_not_inherit_claude_text_model(monkeypatch):
    captured = {}

    def fake_generate(prompt: str, *, width: int, height: int, model: str = "") -> bytes:
        captured["prompt"] = prompt
        captured["width"] = width
        captured["height"] = height
        captured["model"] = model
        return b"fake-png-bytes"

    monkeypatch.setattr(llm_provider, "get_active_provider", lambda: "claude")
    monkeypatch.setattr(llm_provider, "get_active_model", lambda: "opus")
    monkeypatch.setattr(codex_image_provider, "generate_image_bytes_with_codex", fake_generate)

    youtube = YouTube.__new__(YouTube)
    data = youtube._try_codex_cli_image("cinematic star field", 1080, 1920)

    assert data == b"fake-png-bytes"
    assert captured["model"] == ""
    assert captured["prompt"] == "cinematic star field"
    assert captured["width"] == 1080
    assert captured["height"] == 1920


def test_codex_image_provider_can_inherit_openai_text_model(monkeypatch):
    captured = {}

    def fake_generate(prompt: str, *, width: int, height: int, model: str = "") -> bytes:
        captured["model"] = model
        return b"fake-png-bytes"

    monkeypatch.setattr(llm_provider, "get_active_provider", lambda: "openai")
    monkeypatch.setattr(llm_provider, "get_active_model", lambda: "gpt-5.5")
    monkeypatch.setattr(codex_image_provider, "generate_image_bytes_with_codex", fake_generate)

    youtube = YouTube.__new__(YouTube)
    youtube._try_codex_cli_image("cinematic star field", 1080, 1920)

    assert captured["model"] == "gpt-5.5"
