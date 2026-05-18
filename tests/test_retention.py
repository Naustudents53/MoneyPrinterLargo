import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.Retention import CosmicRetentionEngine
from classes.RetentionLab import RetentionLab
from utils import clean_script_for_tts, strip_narration_structure_labels


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


def test_hook_lab_retries_until_hook_passes_threshold():
    calls = []
    responses = [
        "Hoy veremos una historia sobre Jupiter.\nEl planeta cambia en el primer segundo.",
        "Pero el cometa rompe Jupiter y revela una nube imposible?\nNadie ve el cometa romper Jupiter hasta que revela sombra.",
    ]

    def fake_generate(prompt):
        calls.append(prompt)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    hook, report = RetentionLab.select_best_hook(
        topic="El cometa Shoemaker Levy golpea Jupiter",
        niche="espacio",
        language="espanol",
        generate_response=fake_generate,
        candidates=4,
        max_rounds=4,
    )

    assert report["accepted"]
    assert report["rounds"] == 2
    assert report["best_score"] >= RetentionLab.HOOK_SCORE_THRESHOLD
    assert hook.startswith("Pero el cometa")
    assert "RETRY MODE" in calls[1]


def test_hook_lab_fallback_repairs_after_exhausted_model_rounds():
    calls = []

    def fake_generate(prompt):
        calls.append(prompt)
        return "Hoy veremos una historia sobre Jupiter.\nEl planeta cambia en el primer segundo."

    hook, report = RetentionLab.select_best_hook(
        topic="Sistema de Jupiter y observatorios astronomicos de la Tierra, julio de 1994",
        niche="espacio",
        language="espanol",
        generate_response=fake_generate,
        candidates=4,
        max_rounds=2,
    )

    assert len(calls) == 2
    assert report["accepted"]
    assert report["fallback_used"]
    assert report["best_score"] >= RetentionLab.HOOK_SCORE_THRESHOLD
    assert "jupiter" in RetentionLab.normalize(hook)


def test_educational_hook_lab_prefers_named_subject_opening():
    def fake_generate(_prompt):
        return (
            "Nadie ve TON devorar luz antes de apagarse.\n"
            "TON seis dieciocho es un agujero negro que devora luz."
        )

    hook, report = RetentionLab.select_best_hook(
        topic="TON 618: el agujero negro mas grande conocido",
        niche="espacio",
        language="espanol",
        generate_response=fake_generate,
        candidates=4,
        max_rounds=1,
        educational_anchor=True,
    )

    assert report["accepted"]
    assert report["educational_anchor"]
    assert hook.startswith("TON seis dieciocho")


def test_narration_structure_labels_are_stripped_before_tts():
    raw = (
        "Primera revelacion: jupiter se oscurece en silencio. "
        "Segunda revelacion: la nube rompe la luz."
    )

    cleaned = strip_narration_structure_labels(raw)

    assert "revelacion:" not in RetentionLab.normalize(cleaned)
    assert cleaned.startswith("Jupiter se oscurece")
    assert "La nube rompe" in cleaned
    assert clean_script_for_tts(raw) == cleaned


def test_retention_score_flags_spoken_structure_labels():
    report = RetentionLab.score_short_script(
        "Primera revelacion: Jupiter se oscurece en silencio. La nube rompe la luz.",
        topic="Jupiter",
        niche="espacio",
        language="espanol",
        retention_mode="maxima_retencion",
    )

    assert any("structural labels" in issue for issue in report["issues"])


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
