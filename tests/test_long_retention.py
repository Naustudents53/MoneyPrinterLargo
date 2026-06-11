import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import LongRetention as lr


GOOD_INTRO = (
    "Una sombra imposible cruzo el telescopio antes de que nadie pudiera explicarla. "
    "Esta noche vas a descubrir por que tres observatorios borraron sus propios datos. "
    "Pero hay un detalle que no encaja en ningun registro oficial. "
    "Y aqui es donde la historia se vuelve imposible de ignorar. "
    "Lo que encontraron despues, nadie estaba preparado para contarlo. "
    "Quedate, porque la respuesta cambia todo lo que creias saber."
)

WEAK_INTRO = (
    "Sabias que el espacio es muy grande y tiene muchas estrellas. "
    "En este video vamos a hablar del telescopio. "
    "Es un tema muy interesante y muy importante. "
    "Dale like y suscribete al canal y activa la campanita."
)


def _script(intro, sections=None, outro=None):
    sections = sections or [
        "El observatorio detecto la anomalia en pleno invierno. Pero nadie aviso a la prensa.",
        "Los registros mostraban un patron extrano. La pregunta era quien lo habia borrado?",
    ]
    body = "\n".join(
        f"[SECTION {i + 1}: tema]\n{text}" for i, text in enumerate(sections)
    )
    outro = outro or (
        "Gracias por ver el video. Si te gusto dale me gusta, "
        "suscribete al canal y activa la campanita. Hasta la proxima."
    )
    return f"[INTRO]\n{intro}\n{body}\n[CLOSING]\nLa sombra sigue ahi, esperando.\n[OUTRO]\n{outro}"


# --- split_blocks ---------------------------------------------------------


def test_split_blocks_parses_markers():
    blocks = lr.split_blocks(_script(GOOD_INTRO))
    labels = [b["label"] for b in blocks]
    assert labels[0] == "INTRO"
    assert any(l.startswith("SECTION 1") for l in labels)
    assert labels[-1] == "OUTRO"


def test_split_blocks_falls_back_to_paragraphs():
    blocks = lr.split_blocks("Primer parrafo.\n\nSegundo parrafo.")
    assert len(blocks) == 2
    assert blocks[0]["label"] == "PARA 1"


# --- cold open ------------------------------------------------------------


def test_cold_open_rewards_strong_hook():
    report = lr.score_cold_open(GOOD_INTRO)
    assert report["score"] >= 8.0
    assert report["issues"] == []


def test_cold_open_flags_banned_opener():
    report = lr.score_cold_open(WEAK_INTRO)
    assert report["score"] < 7.0
    assert any("generic opener" in issue for issue in report["issues"])


# --- CTA placement --------------------------------------------------------


def test_cta_guard_flags_early_like_ask():
    script = _script(WEAK_INTRO)  # like+subscribe inside the intro
    report = lr.score_cta_placement(script, intro_text=WEAK_INTRO)
    assert report["score"] < 7.0
    assert any("intro" in issue for issue in report["issues"])


def test_cta_guard_accepts_outro_only_asks():
    script = _script(GOOD_INTRO)
    report = lr.score_cta_placement(script)
    assert report["score"] >= 9.0


# --- overall --------------------------------------------------------------


def test_score_long_script_accepts_well_built_script():
    report = lr.score_long_script(_script(GOOD_INTRO), topic="la sombra del telescopio")
    assert report["accepted"] is True
    assert report["intro_score"] >= 8.0


def test_score_long_script_rejects_weak_script():
    report = lr.score_long_script(_script(WEAK_INTRO))
    assert report["accepted"] is False
    assert report["issues"]


# --- rewrite_intro --------------------------------------------------------


def test_rewrite_intro_replaces_only_the_intro_when_better():
    script = _script(WEAK_INTRO)
    report = lr.score_long_script(script)

    def fake_llm(_prompt):
        return GOOD_INTRO

    rewritten, applied = lr.rewrite_intro(script, report, "el telescopio", "Spanish", fake_llm)
    assert applied is True
    assert GOOD_INTRO.split(".")[0] in rewritten
    assert "[SECTION 1" in rewritten  # rest of the script untouched
    assert "Gracias por ver el video" in rewritten


def test_rewrite_intro_keeps_script_when_candidate_is_worse():
    script = _script(GOOD_INTRO)
    report = lr.score_long_script(script)
    rewritten, applied = lr.rewrite_intro(script, report, "tema", "Spanish", lambda _p: WEAK_INTRO)
    assert applied is False
    assert rewritten == script


def test_rewrite_intro_survives_llm_failure():
    script = _script(WEAK_INTRO)
    report = lr.score_long_script(script)

    def boom(_prompt):
        raise RuntimeError("cli down")

    rewritten, applied = lr.rewrite_intro(script, report, "tema", "Spanish", boom)
    assert applied is False
    assert rewritten == script
