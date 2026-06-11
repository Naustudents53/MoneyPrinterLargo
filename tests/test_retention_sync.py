import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes import RetentionSync as rs
from classes import LearningCoach as lc


# --- pure parsers ---------------------------------------------------------


def test_extract_video_id_handles_common_url_shapes():
    assert rs.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert rs.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert rs.extract_video_id("https://youtube.com/shorts/abc123DEF45") == "abc123DEF45"
    assert rs.extract_video_id("uploading...") == ""
    assert rs.extract_video_id("") == ""


def test_extract_avg_percentage_english_and_spanish():
    assert rs.extract_avg_percentage("Average percentage viewed\n43.2%") == 43.2
    assert rs.extract_avg_percentage("Porcentaje promedio reproducido 38,5 %") == 38.5
    assert rs.extract_avg_percentage("no retention metrics here") is None
    # Out-of-range junk is rejected.
    assert rs.extract_avg_percentage("average percentage viewed 740%") is None


def test_curve_from_svg_path_normalizes_and_inverts_y():
    # SVG y grows downward: y=0 is the top (max retention), y=100 the bottom.
    d = "M0,0 L50,20 L100,100"
    curve = rs.curve_from_svg_path(d)
    assert len(curve) == rs.CURVE_SAMPLES
    assert curve[0]["position"] == 0.0
    assert curve[0]["retention"] == 100.0  # starts at the top
    assert curve[-1]["retention"] == 0.0   # ends at the bottom
    # Monotonic decline for this path.
    retentions = [p["retention"] for p in curve]
    assert retentions == sorted(retentions, reverse=True)


def test_curve_from_svg_path_rejects_garbage():
    assert rs.curve_from_svg_path("") == []
    assert rs.curve_from_svg_path("M5,5") == []
    assert rs.curve_from_svg_path("not a path at all") == []


def test_pick_retention_path_prefers_most_points():
    tick = "M0,10 L5,10"
    line = "M0,0 L10,5 L20,9 L30,14 L40,30 L50,31"
    assert rs.pick_retention_path([tick, line]) == line
    assert rs.pick_retention_path([]) == ""


def test_biggest_drop_finds_worst_cliff():
    curve = [
        {"position": 0.0, "retention": 100.0},
        {"position": 0.25, "retention": 92.0},
        {"position": 0.5, "retention": 60.0},   # -32 cliff here
        {"position": 0.75, "retention": 55.0},
    ]
    worst = rs.biggest_drop(curve)
    assert worst["position"] == 0.5
    assert worst["drop"] == 32.0
    assert rs.biggest_drop([]) == {"position": 0.0, "drop": 0.0}


# --- cache plumbing -------------------------------------------------------


def test_store_retention_updates_matching_videos(tmp_path, monkeypatch):
    import cache

    yt_cache = tmp_path / "youtube.json"
    yt_cache.write_text(json.dumps({
        "accounts": [{
            "id": "acc-1",
            "videos": [
                {"url": "https://youtu.be/dQw4w9WgXcQ", "subject": "a"},
                {"url": "https://youtu.be/zzzzzzzzzzz", "subject": "b"},
            ],
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(cache, "get_youtube_cache_path", lambda: str(yt_cache))

    written = rs.store_retention("acc-1", {
        "dQw4w9WgXcQ": {"avg_percentage_viewed": 41.5},
    })
    assert written == 1

    data = json.loads(yt_cache.read_text(encoding="utf-8"))
    videos = data["accounts"][0]["videos"]
    assert videos[0]["avg_percentage_viewed"] == 41.5
    assert "avg_percentage_viewed" not in videos[1]


def test_store_retention_noop_for_other_accounts(tmp_path, monkeypatch):
    import cache

    yt_cache = tmp_path / "youtube.json"
    yt_cache.write_text(json.dumps({
        "accounts": [{"id": "other", "videos": [{"url": "https://youtu.be/dQw4w9WgXcQ"}]}],
    }), encoding="utf-8")
    monkeypatch.setattr(cache, "get_youtube_cache_path", lambda: str(yt_cache))

    assert rs.store_retention("acc-1", {"dQw4w9WgXcQ": {"avg_percentage_viewed": 10}}) == 0


# --- LearningCoach integration --------------------------------------------


def _video(subject, views, **extra):
    video = {
        "subject": subject,
        "title": subject,
        "url": f"https://youtube.com/watch?v={abs(hash(subject)) % 10**11:011d}",
        "view_count": views,
    }
    video.update(extra)
    return video


def test_data_signature_changes_when_retention_arrives():
    base = [_video("black holes", 1500)]
    with_retention = [_video("black holes", 1500, avg_percentage_viewed=44.0)]
    assert lc.data_signature(base) != lc.data_signature(with_retention)


def test_reflection_prompt_surfaces_retention_and_drop():
    videos = [_video(
        "black holes", 1500,
        avg_percentage_viewed=44.0,
        retention_biggest_drop={"position": 0.25, "drop": 18.0},
    )]
    prompt = lc.build_reflection_prompt({"nickname": "Cosmos"}, videos, {})
    assert "44% avg viewed" in prompt
    assert "drop 18.0pts at 25% of the video" in prompt


def test_reflection_prompt_ignores_small_drops():
    videos = [_video(
        "black holes", 1500,
        avg_percentage_viewed=44.0,
        retention_biggest_drop={"position": 0.5, "drop": 2.0},
    )]
    prompt = lc.build_reflection_prompt({"nickname": "Cosmos"}, videos, {})
    assert "biggest drop" not in prompt
