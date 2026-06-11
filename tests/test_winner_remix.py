import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import WinnerRemix as wr


class FakeRng:
    """Deterministic stand-in for random.

    - random() returns a fixed value (for should_remix).
    - choices() picks the highest-weight element so weighting is assertable.
    """

    def __init__(self, value: float = 0.0):
        self._value = value

    def random(self) -> float:
        return self._value

    def choices(self, population, weights, k=1):
        best = max(range(len(population)), key=lambda i: weights[i])
        return [population[best]]


def _short(subject, views, *, url=None, is_remix=False, remix_subtheme=None,
           remix_source_url=None):
    video = {
        "subject": subject,
        "title": subject,
        "url": url or f"https://youtube.com/shorts/{subject.replace(' ', '_')}",
        "view_count": views,
        "is_short": True,
    }
    if is_remix:
        video["is_remix"] = True
    if remix_subtheme is not None:
        video["remix_subtheme"] = remix_subtheme
    if remix_source_url is not None:
        video["remix_source_url"] = remix_source_url
    return video


def test_video_views_parses_and_rejects_garbage():
    assert wr.video_views({"view_count": "1500"}) == 1500
    assert wr.video_views({"view_count": None}) is None
    assert wr.video_views({"view_count": "abc"}) is None
    assert wr.video_views({}) is None


def test_should_remix_uses_ratio_probability():
    # ratio 6 -> threshold 1/6 ~= 0.1667
    assert wr.should_remix(6, rng=FakeRng(0.10)) is True
    assert wr.should_remix(6, rng=FakeRng(0.50)) is False
    # ratio <= 0 disables remixing entirely
    assert wr.should_remix(0, rng=FakeRng(0.0)) is False


def test_pick_winner_returns_none_without_qualifying_winners():
    videos = [_short("tema flojo", 50), _short("otro flojo", 300)]
    assert wr.pick_winner(videos, min_views=1000, rng=FakeRng()) is None


def test_pick_winner_excludes_already_remixed_source():
    winner = _short("TON 618 el agujero negro", 9000,
                    url="https://youtube.com/shorts/ton618")
    # A remix already used TON 618 as its source -> must not be picked again.
    remix = _short("Sagitario A estrella central", 1200, is_remix=True,
                   remix_subtheme="TON 618 el agujero negro",
                   remix_source_url="https://youtube.com/shorts/ton618")
    fresh = _short("Voyager 1 cruza la heliopausa", 5000,
                   url="https://youtube.com/shorts/voyager1")
    picked = wr.pick_winner([winner, remix, fresh], min_views=1000, rng=FakeRng())
    assert picked is not None
    assert picked["url"] == "https://youtube.com/shorts/voyager1"


def test_pick_winner_prefers_higher_weighted_winner():
    low = _short("Encelado luna de Saturno", 1200,
                 url="https://youtube.com/shorts/encelado")
    high = _short("Pulsar PSR B1919", 8000,
                  url="https://youtube.com/shorts/pulsar")
    picked = wr.pick_winner([low, high], min_views=1000, rng=FakeRng())
    assert picked["url"] == "https://youtube.com/shorts/pulsar"


def test_pick_winner_suppresses_subtheme_that_flopped():
    # A past remix of the "Quasar" subtheme flopped (weak views).
    flopped_remix = _short("Quasar lejano apagado", 40, is_remix=True,
                           remix_subtheme="Quasar 3C 273",
                           remix_source_url="https://youtube.com/shorts/old")
    weak_subtheme_winner = _short("Quasar 3C 273 brillante", 1500,
                                  url="https://youtube.com/shorts/quasar")
    other_winner = _short("Titan luna de metano", 1400,
                          url="https://youtube.com/shorts/titan")
    picked = wr.pick_winner(
        [flopped_remix, weak_subtheme_winner, other_winner],
        min_views=1000, rng=FakeRng(),
    )
    # Even though the quasar winner has more views, its subtheme is suppressed,
    # so the other winner wins the weighting.
    assert picked["url"] == "https://youtube.com/shorts/titan"


def test_evaluate_history_classifies_remix_outcomes():
    videos = [
        _short("Quasar brillante", 5000, is_remix=True,
               remix_subtheme="Quasar 3C 273"),
        _short("Pulsar debil", 30, is_remix=True,
               remix_subtheme="Pulsar PSR B1919"),
        _short("No es remix", 9000),  # ignored, not a remix
    ]
    result = wr.evaluate_history(videos)
    assert "Quasar 3C 273" in result["winning_subthemes"]
    assert "Pulsar PSR B1919" in result["weak_subthemes"]


def test_is_acceptable_remix_rejects_duplicate_of_past():
    winner = _short("TON 618 el agujero negro", 9000)
    candidate = "Oumuamua el visitante interestelar"
    past = ["Oumuamua, el objeto que desconcerto a la NASA"]
    assert wr.is_acceptable_remix(candidate, winner, past) is False


def test_is_acceptable_remix_rejects_same_named_subject_as_winner():
    winner = _short("TON 618 el agujero negro mas masivo", 9000)
    # Same distinctive anchor (TON 618) as the winner -> too obvious a repeat.
    candidate = "La historia oculta de TON 618"
    assert wr.is_acceptable_remix(candidate, winner, []) is False


def test_is_acceptable_remix_accepts_different_subject_same_subtheme():
    winner = _short("TON 618 el agujero negro mas masivo", 9000)
    candidate = "Sagitario A: el agujero negro en el centro de la galaxia"
    assert wr.is_acceptable_remix(candidate, winner, []) is True


def test_evaluate_history_ignores_remixes_without_recorded_subtheme():
    """A remix's own subject is NOT a subtheme; no fallback bias allowed."""
    videos = [_short("Quasar lejano apagado", 30, is_remix=True)]
    result = wr.evaluate_history(videos)
    assert result["winning_subthemes"] == set()
    assert result["weak_subthemes"] == set()


def test_pick_winner_penalty_wins_over_boost_for_same_subtheme():
    """A subtheme that both won and flopped must be penalized, not 0.2*2.0."""
    won_remix = _short("Quasar gemelo brillante", 5000, is_remix=True,
                       remix_subtheme="Quasar 3C 273",
                       remix_source_url="https://youtube.com/shorts/a")
    flopped_remix = _short("Quasar lejano apagado", 40, is_remix=True,
                           remix_subtheme="Quasar 3C 273",
                           remix_source_url="https://youtube.com/shorts/b")
    quasar_winner = _short("Quasar 3C 273 brillante", 4000,
                           url="https://youtube.com/shorts/quasar")
    other_winner = _short("Titan luna de metano", 1400,
                          url="https://youtube.com/shorts/titan")
    picked = wr.pick_winner(
        [won_remix, flopped_remix, quasar_winner, other_winner],
        min_views=1000, rng=FakeRng(),
    )
    # 4000 * 0.2 = 800 < 1400 -> the flop penalty must dominate.
    assert picked["url"] == "https://youtube.com/shorts/titan"


def test_build_remix_prompt_places_directive_before_output_format():
    winner = _short("TON 618 el agujero negro mas masivo", 9000)
    directive = "LEARNED PLAYBOOK (apply what has worked):\nHook: empieza con cifra"
    prompt = wr.build_remix_prompt(
        winner, "documentales del universo", "Spanish", directive=directive
    )
    assert "LEARNED PLAYBOOK" in prompt
    assert prompt.index("LEARNED PLAYBOOK") < prompt.index("OUTPUT FORMAT")


def test_build_remix_prompt_mentions_winner_and_language():
    winner = _short("TON 618 el agujero negro mas masivo", 9000)
    prompt = wr.build_remix_prompt(winner, "documentales del universo", "Spanish")
    assert "TON 618" in prompt
    assert "Spanish" in prompt
    assert "documentales del universo" in prompt
