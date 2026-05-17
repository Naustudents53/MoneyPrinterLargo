import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.PhotoPromptGenerator import PhotoPromptGenerator


def test_photo_prompt_generator_uses_generated_topic():
    calls = []

    def fake_llm(prompt: str, temperature: float = 0.7) -> str:
        calls.append(prompt)
        if "Generate ONE specific" in prompt:
            return "Voyager 1: la nave que sigue hablando desde el borde del sistema solar"
        if "reference narration script" in prompt:
            return (
                "Voyager 1 cruza una frontera invisible. "
                "Su antena todavia apunta hacia la Tierra. "
                "La senal tarda horas en volver. "
                "El silencio alrededor vuelve pequena nuestra idea del Sol."
            )
        if "visual research assistant" in prompt:
            return '{"setting":"interstellar space and NASA mission control","visual_anchors":"Voyager 1, dish antenna, gold record, heliopause, deep space signal","must_avoid":"random radio telescope, messy desk, team meeting"}'
        if "MoneyPrinter project image prompts" in prompt:
            return '["Voyager 1 crosses the heliopause with its dish antenna angled toward a distant pale Sun, the gold record glinting against black interstellar space, faint plasma waves rippling around the probe, one clear spacecraft silhouette carrying the section\\u2019s invisible-boundary idea."]'
        return "[]"

    result = PhotoPromptGenerator(text_generator=fake_llm).generate(
        topic="",
        count=1,
        channel={
            "id": "ch1",
            "nickname": "Universo",
            "niche": "documentales del universo y astronomia",
            "language": "espanol",
            "image_style": "ultra-realistic astrophotography",
        },
    )

    assert result.generated_topic is True
    assert result.topic.startswith("Voyager 1")
    assert "CANAL: Universo" in result.text
    assert "TEMA: Voyager 1" in result.text
    assert "Project scene prompt:" in result.text
    assert "Positive prompt:" in result.text
    assert "Negative prompt:" in result.text
    assert "random radio telescope" in result.text
    assert len(calls) >= 4


def test_photo_prompt_generator_falls_back_when_llm_output_is_incomplete():
    def fake_llm(prompt: str, temperature: float = 0.7) -> str:
        return "too short"

    result = PhotoPromptGenerator(text_generator=fake_llm).generate(
        topic="El archivo secreto de una civilizacion antigua",
        count=2,
        style="dark_mystery",
        aspect_ratio="16:9",
    )

    assert result.generated_topic is False
    assert result.count == 2
    assert result.text.count("Positive prompt:") == 2
    assert result.text.count("Negative prompt:") == 2
    assert result.text.count("Project scene prompt:") == 2
    assert "TEMA: El archivo secreto de una civilizacion antigua" in result.text
