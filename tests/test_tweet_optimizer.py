import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.TweetOptimizer import ViralTweetOptimizer


def test_parse_candidates_from_strict_json():
    raw = json.dumps(
        {
            "candidates": [
                {"tweet": "AI agents fail when the task is vague; the fix is a crisp success test."},
                {"tweet": "The fastest prompt upgrade: define what a bad answer looks like first."},
            ]
        }
    )

    parsed = ViralTweetOptimizer.parse_candidates(raw)

    assert len(parsed) == 2
    assert parsed[0].startswith("AI agents fail")


def test_optimizer_prefers_specific_replyable_candidate():
    raw = json.dumps(
        {
            "candidates": [
                {"tweet": "AI is changing the game for everyone. Follow for more tips!"},
                {
                    "tweet": (
                        "Most AI workflows fail at step 2: nobody defines the rejection test. "
                        "What would you measure before trusting the output?"
                    )
                },
            ]
        }
    )

    selection = ViralTweetOptimizer.generate(
        topic="AI workflow automation",
        language="English",
        recent_posts=[],
        generate_response=lambda _prompt: raw,
    )

    assert "rejection test" in selection.tweet
    assert selection.score.reply > 0.4
    assert selection.score.negative < 0.35


def test_recent_duplicate_is_penalized():
    recent = [
        "Most AI workflows fail at step 2: nobody defines the rejection test. "
        "What would you measure before trusting the output?"
    ]
    duplicate = ViralTweetOptimizer.score_tweet(recent[0], "AI workflow automation", recent)
    fresh = ViralTweetOptimizer.score_tweet(
        "The underrated AI skill is saying no: reject outputs that cannot cite the exact source of truth.",
        "AI workflow automation",
        recent,
    )

    assert duplicate.duplicate_penalty > 0.2
    assert fresh.total > duplicate.total


def test_clean_tweet_keeps_one_hashtag_and_limit():
    text = (
        "Tweet: This launch has one useful question: what breaks first when users arrive? "
        "#buildinpublic #startup #ai "
        + "extra " * 80
    )

    cleaned = ViralTweetOptimizer.clean_tweet(text)

    assert len(cleaned) <= 260
    assert cleaned.count("#") <= 1
    assert not cleaned.lower().startswith("tweet:")


def test_generation_failure_returns_empty_selection():
    selection = ViralTweetOptimizer.generate(
        topic="AI workflow automation",
        language="English",
        recent_posts=[],
        generate_response=lambda _prompt: None,
    )

    assert selection.tweet == ""
    assert selection.score.total < 0
