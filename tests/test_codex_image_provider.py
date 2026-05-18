import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import codex_image_provider


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def test_generate_image_bytes_with_codex_reads_created_png(monkeypatch):
    captured = {}

    def fake_run(args, input, **kwargs):
        captured["args"] = args
        captured["input"] = input
        captured["kwargs"] = kwargs
        marker = "Save the final image file here:\n"
        output_path = Path(input.split(marker, 1)[1].split("\n", 1)[0].strip())
        img = Image.new("RGB", (512, 512))
        for x in range(512):
            for y in range(512):
                img.putpixel((x, y), ((x * 3) % 255, (y * 5) % 255, (x + y) % 255))
        img.save(output_path)
        message_path = Path(args[args.index("--output-last-message") + 1])
        message_path.write_text("DONE", encoding="utf-8")
        return _Completed()

    monkeypatch.setattr(codex_image_provider, "get_codex_cli_command", lambda: "codex")
    monkeypatch.setattr(codex_image_provider, "get_codex_cli_model", lambda: "")
    monkeypatch.setattr(codex_image_provider, "get_codex_cli_image_sandbox", lambda: "workspace-write")
    monkeypatch.setattr(codex_image_provider, "get_codex_cli_image_timeout_seconds", lambda: 321)
    monkeypatch.setattr(codex_image_provider, "get_openai_reasoning_effort", lambda: "high")
    monkeypatch.setattr(subprocess, "run", fake_run)

    data = codex_image_provider.generate_image_bytes_with_codex(
        "cinematic black hole accretion disk",
        width=1080,
        height=1920,
        model="gpt-test",
    )

    assert data.startswith(b"\x89PNG")
    assert captured["args"][:3] == ["codex", "-c", 'model_reasoning_effort="high"']
    assert captured["args"][captured["args"].index("--ask-for-approval") + 1] == "never"
    assert captured["args"][captured["args"].index("--sandbox") + 1] == "workspace-write"
    assert captured["args"][captured["args"].index("--model") + 1] == "gpt-test"
    assert captured["kwargs"]["timeout"] == 321
    assert "cinematic black hole accretion disk" in captured["input"]
    assert "1080x1920px" in captured["input"]
