import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import LearningCoach as lc


def _video(subject, views, *, url=None, synced="2026-06-01T00:00:00Z"):
    return {
        "subject": subject,
        "title": subject,
        "url": url or f"https://youtube.com/shorts/{subject.replace(' ', '_')}",
        "view_count": views,
        "stats_synced_at": synced,
        "is_short": True,
    }


# --- data_signature / is_reflection_due ----------------------------------


def test_data_signature_is_stable_regardless_of_order():
    a = [_video("black holes", 1500), _video("nebula", 800)]
    b = list(reversed(a))
    assert lc.data_signature(a) == lc.data_signature(b)


def test_data_signature_changes_when_views_change():
    base = [_video("black holes", 1500)]
    bumped = [_video("black holes", 2500)]
    assert lc.data_signature(base) != lc.data_signature(bumped)


def test_data_signature_ignores_sync_timestamp():
    """Same views re-synced later must NOT look like new data (no LLM call)."""
    first = [_video("black holes", 1500, synced="2026-06-01T00:00:00Z")]
    resynced = [_video("black holes", 1500, synced="2026-06-02T00:00:00Z")]
    assert lc.data_signature(first) == lc.data_signature(resynced)


def test_data_signature_empty_when_no_scored_videos():
    assert lc.data_signature([]) == ""
    assert lc.data_signature([{"subject": "x", "view_count": None}]) == ""


def test_is_reflection_due_true_when_signature_is_new():
    videos = [_video("black holes", 1500)]
    learning = {"last_data_signature": "stale-or-missing"}
    assert lc.is_reflection_due(learning, videos) is True


def test_is_reflection_due_false_when_signature_unchanged():
    videos = [_video("black holes", 1500)]
    sig = lc.data_signature(videos)
    learning = {"last_data_signature": sig}
    assert lc.is_reflection_due(learning, videos) is False


def test_is_reflection_due_false_when_nothing_to_learn():
    assert lc.is_reflection_due({}, []) is False


# --- parse_reflection ----------------------------------------------------


def test_parse_reflection_handles_plain_json():
    text = '{"lessons": ["hook fast"], "playbook": {"topic_guidance": "stay cosmic"}}'
    parsed = lc.parse_reflection(text)
    assert parsed["lessons"] == ["hook fast"]
    assert parsed["playbook"]["topic_guidance"] == "stay cosmic"


def test_parse_reflection_handles_fenced_json_with_prose():
    text = (
        "Sure, here is what I learned:\n"
        "```json\n"
        '{"lessons": ["open with a question"], "playbook": {"hook_guidance": "tease"}}\n'
        "```\n"
        "Hope that helps!"
    )
    parsed = lc.parse_reflection(text)
    assert parsed["lessons"] == ["open with a question"]
    assert parsed["playbook"]["hook_guidance"] == "tease"


def test_parse_reflection_returns_empty_on_garbage():
    assert lc.parse_reflection("no json here at all") == {}
    assert lc.parse_reflection("") == {}


# --- merge_lessons -------------------------------------------------------


def test_merge_lessons_dedupes_case_insensitively():
    merged = lc.merge_lessons(["Hook fast"], ["hook fast", "use numbers"], 30)
    assert merged.count("Hook fast") + merged.count("hook fast") == 1
    assert "use numbers" in merged


def test_merge_lessons_caps_to_max_keeping_newest():
    existing = [f"old {i}" for i in range(30)]
    merged = lc.merge_lessons(existing, ["fresh insight"], 5)
    assert len(merged) == 5
    assert "fresh insight" in merged


# --- run_reflection ------------------------------------------------------


def test_run_reflection_merges_and_updates_signature():
    videos = [_video("black holes", 1500)]
    calls = {"n": 0}

    def ask(_prompt):
        calls["n"] += 1
        return '{"lessons": ["lead with stakes"], "playbook": {"avoid": "slow intros"}}'

    out = lc.run_reflection({"nickname": "Cosmos"}, videos, {}, ask)
    assert calls["n"] == 1
    assert "lead with stakes" in out["lessons"]
    assert out["playbook"]["avoid"] == "slow intros"
    assert out["last_data_signature"] == lc.data_signature(videos)


def test_run_reflection_does_not_mark_signature_on_garbage_answer():
    """An unparseable answer must not consume the data: retry next sync."""
    videos = [_video("black holes", 1500)]
    out = lc.run_reflection({}, videos, {"last_data_signature": "prev"}, lambda _p: "totally not json")
    assert out.get("lessons") is None
    assert out["last_data_signature"] == "prev"


def test_run_reflection_does_not_mark_signature_on_empty_answer():
    """A soft CLI failure (empty string) must not consume the data either."""
    videos = [_video("black holes", 1500)]
    out = lc.run_reflection({}, videos, {"last_data_signature": "prev"}, lambda _p: "")
    assert out["last_data_signature"] == "prev"


def test_run_reflection_does_not_mark_signature_when_ask_raises():
    videos = [_video("black holes", 1500)]

    def ask(_prompt):
        raise RuntimeError("claude cli unavailable")

    out = lc.run_reflection({}, videos, {"last_data_signature": "prev"}, ask)
    assert out.get("last_data_signature") == "prev"


# --- injected_directive --------------------------------------------------


def test_injected_directive_includes_playbook_and_lessons():
    learning = {
        "lessons": ["lead with stakes"],
        "playbook": {"topic_guidance": "stay cosmic", "avoid": "slow intros"},
    }
    directive = lc.injected_directive(learning)
    assert "stay cosmic" in directive
    assert "slow intros" in directive
    assert "lead with stakes" in directive


def test_injected_directive_empty_when_no_learning():
    assert lc.injected_directive({}) == ""
    assert lc.injected_directive(None) == ""
