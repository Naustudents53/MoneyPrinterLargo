import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.Retention import CosmicRetentionEngine
from classes.RetentionLab import RetentionLab


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


def test_retention_plan_covers_retention_pro_outputs():
    script = (
        "El Sol se traga un planeta entero en segundos. "
        "Primero la atmosfera se quema como papel. "
        "Pero el detalle oculto es la gravedad deformando la orbita. "
        "Nadie ve el choque hasta que el borde empieza a romperse. "
        "Por eso el primer segundo vuelve a parecer una amenaza."
    )
    plan = RetentionLab.build_retention_plan(
        script=script,
        topic="El Sol se traga a un planeta entero en segundos",
        niche="espacio",
        language="espanol",
        retention_mode="maxima_retencion",
        retention_preflight={"final_score": 8.7, "accepted": True},
        retention_hook_lab={
            "best_hook": "El Sol se traga un planeta entero en segundos.",
            "best_score": 9.0,
            "candidates": [
                {"hook": "El Sol se traga un planeta entero en segundos.", "score": 9.0},
                {"hook": "Nadie sobrevive cuando el Sol cambia de tamano.", "score": 8.1},
            ],
        },
        visual_beat_map=[
            {"beat": "scroll stopper", "visual_goal": "Planet near the Sun", "motion": "burns"},
            {"beat": "scale jump", "visual_goal": "Atmosphere strips away", "motion": "tears"},
            {"beat": "hidden force", "visual_goal": "Orbit bends", "motion": "bends"},
        ],
        visual_beat_report={"accepted": True, "count": 3},
        visual_preflight={"score": 7.8},
        history_videos=[
            {
                "is_short": True,
                "title": "El Sol oculto #shorts",
                "subject": "El Sol oculto",
                "view_count": 1600,
                "date": "2026-01-01",
            },
            {
                "is_short": True,
                "title": "El planeta perdido #shorts",
                "subject": "El planeta perdido",
                "view_count": 40,
                "date": "2026-01-02",
            },
        ],
    )

    assert plan["status"] in {"pass", "warn"}
    assert plan["hook_0_3s"]["score"] == 9.0
    assert plan["micro_hooks"]
    assert "traga" in plan["hot_words"]
    assert plan["hook_ab_tests"]

    compact = RetentionLab.compact_retention_plan(plan)
    assert compact["score"] == plan["overall_score"]
    assert compact["micro_hooks_count"] == len(plan["micro_hooks"])
