import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from llm_provider import normalize_gemini_model_id


def test_normalizes_legacy_gemma_gemini_ids():
    assert normalize_gemini_model_id("gemma-4-31b") == "gemma-4-31b-it"
    assert normalize_gemini_model_id("gemma-4-26b") == "gemma-4-26b-a4b-it"


def test_normalizes_ollama_gemma_tags_when_forced_to_gemini():
    assert normalize_gemini_model_id("gemma4:31b-cloud") == "gemma-4-31b-it"
    assert normalize_gemini_model_id("gemma4-26b:cloud") == "gemma-4-26b-a4b-it"


def test_leaves_valid_gemini_ids_unchanged():
    assert normalize_gemini_model_id("gemini-2.5-flash") == "gemini-2.5-flash"
