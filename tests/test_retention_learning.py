"""Tests for the LearningCoach -> RetentionLab loop and burned-term decay."""

import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.RetentionLab import RetentionLab


HOOK = "Nadie vio la sombra del cometa romper la luz aquella noche"


def test_score_hook_penalizes_learned_avoid_terms():
    base = RetentionLab.score_hook(HOOK, topic="el cometa oscuro")
    penalized = RetentionLab.score_hook(
        HOOK, topic="el cometa oscuro", avoid_terms=["sombra"]
    )
    assert penalized["score"] < base["score"]
    assert penalized["metrics"]["learned_avoid_hits"] == 1
    assert any("historically underperform" in i for i in penalized["issues"])


def test_score_hook_boosts_learned_boost_terms():
    base = RetentionLab.score_hook(HOOK, topic="el cometa oscuro")
    boosted = RetentionLab.score_hook(
        HOOK, topic="el cometa oscuro", boost_terms=["cometa"]
    )
    assert boosted["score"] >= base["score"]
    assert boosted["metrics"]["learned_boost_hits"] == 1


def test_score_short_script_applies_learned_terms():
    script = (
        "Nadie vio la sombra del cometa romper la luz. "
        "Pero el cometa oculta un nucleo imposible que devora el cielo. "
        "Por eso la sombra vuelve cada noche."
    )
    base = RetentionLab.score_short_script(script, topic="el cometa oscuro")
    penalized = RetentionLab.score_short_script(
        script, topic="el cometa oscuro", avoid_terms=["sombra"]
    )
    assert penalized["score"] < base["score"]


# --- burned-term time decay -------------------------------------------------


def _video(subject, views, *, days_ago):
    date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "subject": subject,
        "title": subject,
        "url": f"https://youtube.com/shorts/{abs(hash(subject + str(days_ago)))}",
        "view_count": views,
        "date": date,
        "is_short": True,
    }


def test_old_flops_no_longer_burn_a_term():
    videos = [
        _video("quasar lejano apagado", 20, days_ago=400),
        _video("quasar distante sin brillo", 30, days_ago=400),
    ]
    burned = RetentionLab.burned_terms(videos)
    assert burned == []


def test_recent_flops_still_burn_a_term():
    videos = [
        _video("quasar lejano apagado", 20, days_ago=10),
        _video("quasar distante sin brillo", 30, days_ago=20),
    ]
    burned = RetentionLab.burned_terms(videos)
    assert any(item["term"] == "quasar" for item in burned)
