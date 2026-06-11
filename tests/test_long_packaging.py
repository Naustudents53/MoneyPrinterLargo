import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import LongPackaging as lp


# --- score_title -----------------------------------------------------------


def test_score_title_rewards_specific_curious_title():
    report = lp.score_title(
        "El error OLVIDADO que hundio al imperio bizantino en 1453",
        topic="la caida del imperio bizantino en 1453",
    )
    assert report["score"] >= 7.0
    assert "uses overused term" not in " ".join(report["issues"])


def test_score_title_penalizes_secreto_and_caps_spam():
    report = lp.score_title(
        "EL SECRETO INCREIBLE QUE NADIE SABE!!!",
        topic="la caida del imperio bizantino",
    )
    assert report["score"] < 5.0
    issues = " ".join(report["issues"])
    assert "secreto" in issues
    assert "ALL-CAPS" in issues
    assert "exclamation" in issues


def test_score_title_penalizes_overlong_titles():
    long_title = "Una historia larguisima sobre el imperio bizantino " * 3
    report = lp.score_title(long_title, topic="imperio bizantino")
    assert any("longer than" in i for i in report["issues"])


def test_score_title_flags_offtopic_title():
    report = lp.score_title("La VERDAD sobre los dinosaurios gigantes", topic="el imperio bizantino")
    assert any("does not name anything from the topic" in i for i in report["issues"])


# --- select_best_title -----------------------------------------------------


def test_select_best_title_picks_highest_scoring_candidate():
    def fake_llm(_prompt):
        return (
            "EL SECRETO INCREIBLE QUE NADIE SABE\n"
            "La noche OLVIDADA en que el imperio bizantino dejo de existir\n"
            "Video interesante\n"
        )

    best, report = lp.select_best_title("el imperio bizantino", "Spanish", fake_llm)
    assert "bizantino" in best.lower()
    # "Video interesante" (2 words) is filtered out as too short to be a title
    assert report["candidate_count"] == 2
    assert report["best_score"] == report["candidates"][0]["score"]


def test_select_best_title_returns_empty_on_llm_failure():
    def boom(_prompt):
        raise RuntimeError("cli down")

    best, report = lp.select_best_title("tema", "Spanish", boom)
    assert best == ""
    assert report["accepted"] is False


# --- chapters --------------------------------------------------------------

SCRIPT = (
    "[INTRO]\n" + ("palabra " * 100).strip() + "\n"
    "[SECTION 1: El origen del misterio]\n" + ("palabra " * 200).strip() + "\n"
    "[SECTION 2: La noche del hallazgo]\n" + ("palabra " * 200).strip() + "\n"
    "[SECTION 3: parte 3]\n" + ("palabra " * 200).strip() + "\n"
    "[CLOSING]\n" + ("palabra " * 50).strip() + "\n"
    "[OUTRO]\n" + ("palabra " * 50).strip()
)


def test_build_chapters_maps_word_fractions_to_duration():
    chapters = lp.build_chapters(SCRIPT, audio_duration_seconds=800)
    assert chapters[0] == {"seconds": 0.0, "title": "Introducción"}
    # 100 of 800 words before section 1 -> 1/8 of 800s = 100s
    assert chapters[1]["seconds"] == 100.0
    assert chapters[1]["title"] == "El origen del misterio"
    # placeholder "parte 3" falls back to a generic chapter name
    assert chapters[3]["title"] == "Capítulo 3"
    # CLOSING+OUTRO merge into one final chapter
    assert chapters[-1]["title"] == "Conclusión"
    assert len(chapters) == 5


def test_build_chapters_empty_without_markers_or_duration():
    assert lp.build_chapters("solo texto sin marcadores", 800) == []
    assert lp.build_chapters(SCRIPT, 0) == []
    assert lp.build_chapters(SCRIPT, None) == []


def test_build_chapters_drops_too_close_chapters():
    tiny = (
        "[INTRO]\n" + ("palabra " * 100).strip() + "\n"
        "[SECTION 1: a]\n" + "palabra\n"
        "[SECTION 2: b]\n" + ("palabra " * 100).strip() + "\n"
        "[CLOSING]\ncierre final aqui mismo"
    )
    chapters = lp.build_chapters(tiny, audio_duration_seconds=600)
    # section 2 starts <10s after section 1 -> one of them is dropped
    seconds = [c["seconds"] for c in chapters]
    assert all(b - a >= 10 for a, b in zip(seconds, seconds[1:]))


def test_format_timestamp_handles_hours():
    assert lp.format_timestamp(0) == "0:00"
    assert lp.format_timestamp(75) == "1:15"
    assert lp.format_timestamp(3675) == "1:01:15"


def test_chapters_block_renders_youtube_format():
    chapters = lp.build_chapters(SCRIPT, audio_duration_seconds=800)
    block = lp.chapters_block(chapters)
    assert block.startswith("\n\nCapítulos:\n0:00 ")
    assert "1:40 El origen del misterio" in block


def test_chapters_block_empty_for_no_chapters():
    assert lp.chapters_block([]) == ""
