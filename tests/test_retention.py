import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.Retention import CosmicRetentionEngine


def test_detects_cosmic_context_from_topic_and_niche():
    assert CosmicRetentionEngine.is_cosmic_context(
        "TON 618: el agujero negro mas grande conocido",
        "documentales del universo",
    )
    assert CosmicRetentionEngine.is_cosmic_context(
        "La senal Wow y el silencio del cosmos",
        "",
    )
    assert not CosmicRetentionEngine.is_cosmic_context(
        "La caida de Constantinopla",
        "historia medieval",
    )


def test_cosmic_directives_only_apply_to_cosmic_topics():
    cosmic = CosmicRetentionEngine.short_generation_directive(
        "Voyager 1 cruzo la heliopausa",
        "astronomia",
        "Spanish",
    )
    non_cosmic = CosmicRetentionEngine.short_generation_directive(
        "El comercio de especias en Venecia",
        "historia",
        "Spanish",
    )

    assert "COSMIC RETENTION PROFILE" in cosmic
    assert non_cosmic == ""


def test_retention_score_rewards_mystery_visuals_and_pacing():
    flat = "Hoy hablaremos sobre agujeros negros. Son objetos con mucha gravedad. Estan en el espacio."
    strong = (
        "Un agujero negro no es un agujero, es una frontera. "
        "La luz se dobla en su horizonte. "
        "El disco brilla mientras la gravedad borra cualquier escape. "
        "Tal vez lo mas inquietante es que alli el futuro apunta hacia adentro."
    )

    assert CosmicRetentionEngine.score_script(strong).average > CosmicRetentionEngine.score_script(flat).average


def test_optimize_short_script_keeps_original_when_sentence_count_changes():
    original = "Uno. Dos. Tres."

    def fake_generate(_prompt):
        return "Uno mejorado. Dos mejorado."

    assert CosmicRetentionEngine.optimize_short_script(
        script=original,
        topic="agujero negro",
        niche="universo",
        language="Spanish",
        sentence_length=3,
        target_words=None,
        generate_response=fake_generate,
    ) == original
