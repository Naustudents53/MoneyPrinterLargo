import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.NarrationVoice import NarrationVoice


def test_short_voice_is_a_guardrail_not_rewrite_brief():
    directive = NarrationVoice.short_generation_directive("Espanol")

    assert "guardrail" in directive
    assert "not a separate rewrite brief" in directive
    assert "cause, consequence, and reveal" in directive
    assert "No calls to action" in directive


def test_rewrite_guardrail_preserves_existing_voice():
    directive = NarrationVoice.rewrite_guardrail("Espanol")

    assert "Preserve the original narrator voice" in directive
    assert "Change only what helps" in directive
    assert "hype phrases" in directive


def test_long_voice_keeps_outro_brief_when_required():
    directive = NarrationVoice.long_generation_directive("Espanol")

    assert "DOCUMENTARY VOICE GUIDE" in directive
    assert "outro call to action is required" in directive
    assert "does not break the story" in directive
