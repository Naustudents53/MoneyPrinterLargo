import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.LongScriptShortener import (
    ShortenOptions,
    build_shortening_prompt,
    parse_long_script_text,
    sentence_count,
    shorten_long_script,
)
from scripts.long_script_to_short import build_render_command


SAMPLE_LONG_SCRIPT = """# Topic: GW170817: la kilonova que fabrico oro
# Words: 400
# Estimated duration: ~3 min
# ============================================================

[INTRO]
Aquella manana los detectores escucharon una senal imposible.
Dos estrellas de neutrones chocaron y abrieron una pista sobre el oro.

[SECTION 1: La grieta dorada]
El cielo de NGC 4993 mostro una brasa nueva.
El color paso de azul a rojo en pocos dias.
La nube se expandia con materia radiactiva.

[SECTION 2: La escala del choque]
Una estrella de neutrones guarda masa enorme en una esfera diminuta.
La colision arranco materia antes de que todo colapsara.
Ese material podia sembrar elementos pesados.

[CLOSING]
La senal unio gravedad, luz y quimica.
Ahora cada atomo de oro parece guardar memoria de esa violencia.

[OUTRO]
Gracias por llegar hasta el final.
Suscribete al canal y activa la campanita.
"""


def test_parse_long_script_extracts_topic_and_omits_outro_from_short_source():
    document = parse_long_script_text(SAMPLE_LONG_SCRIPT)

    assert document.topic == "GW170817: la kilonova que fabrico oro"
    assert "OUTRO" in document.sections
    assert "Suscribete" in document.sections["OUTRO"]
    assert "Suscribete" not in document.source_for_short()
    assert "[SECTION" not in document.source_for_short()


def test_build_prompt_uses_duration_preset_and_blocks_cta():
    document = parse_long_script_text(SAMPLE_LONG_SCRIPT)
    prompt = build_shortening_prompt(
        document,
        ShortenOptions(duration_seconds=120, language="espanol"),
    )

    assert "EXACTLY 22 sentences" in prompt
    assert "about 310 spoken words" in prompt
    assert "Do not include YouTube outro" in prompt
    assert "GW170817: la kilonova que fabrico oro" in prompt


def test_shorten_long_script_cleans_llm_wrappers():
    def fake_llm(_prompt: str, temperature: float = 0.7) -> str:
        return '```text\n"La senal llego primero. Luego el oro revelo su origen."\n```'

    result = shorten_long_script(
        SAMPLE_LONG_SCRIPT,
        ShortenOptions(duration_seconds=60),
        text_generator=fake_llm,
    )

    assert result.used_llm is True
    assert result.script == "La senal llego primero. Luego el oro revelo su origen."
    assert result.duration_seconds == 60


def test_shorten_long_script_falls_back_to_clean_exact_sentence_count():
    def failing_llm(_prompt: str, temperature: float = 0.7) -> str:
        raise RuntimeError("offline")

    result = shorten_long_script(
        SAMPLE_LONG_SCRIPT,
        ShortenOptions(duration_seconds=60),
        text_generator=failing_llm,
    )

    assert result.used_llm is False
    assert sentence_count(result.script) == 12
    assert "Suscribete" not in result.script
    assert "[" not in result.script


def test_cli_no_llm_writes_output_and_preview(tmp_path):
    source = tmp_path / "long.txt"
    output = tmp_path / "short.txt"
    source.write_text(SAMPLE_LONG_SCRIPT, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "long_script_to_short.py"),
            str(source),
            "--duration",
            "60",
            "--output",
            str(output),
            "--no-llm",
            "--preview",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0
    assert output.is_file()
    assert "PREVIEW_ID=" in result.stdout
    assert "mode=fallback" in result.stdout


def test_render_command_uses_preview_script_without_upload_by_default(tmp_path):
    script_file = tmp_path / ".preview-abc123.txt"

    cmd = build_render_command(
        channel_id="channel-123",
        script_file=script_file,
        duration=120,
        topic="Tema corto",
        image_mode="ai",
        image_provider="gemini",
        render_profile="fast",
        upload=False,
        upload_platforms="",
        llm_provider="codex",
        llm_model="gpt-5.4",
        retention_mode="maxima_retencion",
    )

    assert "webapp\\api\\run_job.py" in " ".join(cmd) or "webapp/api/run_job.py" in " ".join(cmd)
    assert cmd[cmd.index("--channel-id") + 1] == "channel-123"
    assert cmd[cmd.index("--duration") + 1] == "120"
    assert cmd[cmd.index("--script-file") + 1] == str(script_file)
    assert cmd[cmd.index("--image-provider") + 1] == "gemini"
    assert cmd[cmd.index("--render-profile") + 1] == "fast"
    assert cmd[cmd.index("--llm-provider") + 1] == "codex"
    assert "--upload" not in cmd


def test_run_job_long_script_preview_prints_preview_id(tmp_path):
    source = tmp_path / "long.txt"
    source.write_text(SAMPLE_LONG_SCRIPT, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "webapp" / "api" / "run_job.py"),
            "long-script-preview",
            "--input",
            str(source),
            "--duration",
            "60",
            "--no-llm",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0
    assert "PREVIEW_ID=" in result.stdout
    assert "mode=fallback" in result.stdout
