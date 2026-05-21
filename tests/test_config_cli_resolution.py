import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import config


def test_resolve_codex_cli_from_openai_desktop_install(monkeypatch, tmp_path):
    localappdata = tmp_path / "LocalAppData"
    codex_exe = localappdata / "OpenAI" / "Codex" / "bin" / "codex.exe"
    codex_exe.parent.mkdir(parents=True)
    codex_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(config.shutil, "which", lambda _candidate: None)

    assert config._resolve_cli_command("codex", "codex") == str(codex_exe)


def test_short_render_size_accepts_env_dimensions(monkeypatch):
    monkeypatch.setenv("MP_SHORT_RENDER_SIZE", "1080x1920")

    assert config.get_short_render_size() == (1080, 1920)


def test_photo_vision_provider_accepts_cli_aliases(monkeypatch):
    monkeypatch.setenv("MP_PHOTO_VISION_PROVIDER", "codex_cli")

    assert config.get_photo_vision_provider() == "codex"


def test_photo_vision_provider_falls_back_to_auto_for_unknown(monkeypatch):
    monkeypatch.setenv("MP_PHOTO_VISION_PROVIDER", "not-real")

    assert config.get_photo_vision_provider() == "auto"


def test_4k_render_defaults_keep_orientation(monkeypatch):
    monkeypatch.setenv("MP_SHORT_RENDER_SIZE", "4k")
    monkeypatch.setenv("MP_LONG_RENDER_SIZE", "4k")

    assert config.get_short_render_size() == (2160, 3840)
    assert config.get_long_render_size() == (3840, 2160)
