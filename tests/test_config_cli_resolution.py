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
