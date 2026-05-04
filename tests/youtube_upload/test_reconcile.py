"""
Tests for `classes.YouTubeUploader.reconcile_pending_uploads`.

A crashed run leaves cache entries with `url == "uploading..."` forever.
The reconciler should mark anything older than the grace window as
`"stale"` so the cache doesn't accumulate placeholders.
"""

import json
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "youtube.json"
    monkeypatch.setattr(
        "classes.YouTubeUploader.get_youtube_cache_path",
        lambda: str(cache_path),
    )
    return str(cache_path)


def _write_cache(path: str, videos: list[dict]) -> None:
    payload = {
        "accounts": [
            {"id": "acc-1", "videos": videos},
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _read_cache(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _ts(hours_ago: int) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def test_marks_old_uploading_as_stale(isolated_cache):
    from classes.YouTubeUploader import reconcile_pending_uploads

    _write_cache(isolated_cache, [
        {"title": "old", "url": "uploading...", "date": _ts(48)},
        {"title": "fresh", "url": "uploading...", "date": _ts(1)},  # within grace
        {"title": "uploaded", "url": "https://youtube.com/watch?v=abc", "date": _ts(72)},
    ])

    patched = reconcile_pending_uploads()
    assert patched == 1

    data = _read_cache(isolated_cache)
    videos = data["accounts"][0]["videos"]
    by_title = {v["title"]: v for v in videos}
    assert by_title["old"]["url"] == "stale"
    assert by_title["fresh"]["url"] == "uploading..."
    assert by_title["uploaded"]["url"].startswith("https://")


def test_no_cache_file_returns_zero(tmp_path, monkeypatch):
    nonexistent = str(tmp_path / "missing.json")
    monkeypatch.setattr(
        "classes.YouTubeUploader.get_youtube_cache_path",
        lambda: nonexistent,
    )
    from classes.YouTubeUploader import reconcile_pending_uploads
    assert reconcile_pending_uploads() == 0


def test_uses_last_seen_at_when_present(isolated_cache):
    """
    If a video has both `date` (creation) and `last_seen_at` (last poll),
    the reconciler should prefer last_seen_at — the user may have
    re-tried after the original date.
    """
    from classes.YouTubeUploader import reconcile_pending_uploads

    _write_cache(isolated_cache, [
        {
            "title": "retried",
            "url": "uploading...",
            "date": _ts(72),         # ancient creation
            "last_seen_at": _ts(1),  # but still being polled
        },
    ])

    assert reconcile_pending_uploads() == 0
    assert _read_cache(isolated_cache)["accounts"][0]["videos"][0]["url"] == "uploading..."


def test_unparseable_timestamp_treated_as_stale(isolated_cache):
    from classes.YouTubeUploader import reconcile_pending_uploads

    _write_cache(isolated_cache, [
        {"title": "garbage", "url": "uploading...", "date": "not-a-date"},
    ])

    assert reconcile_pending_uploads() == 1
    assert _read_cache(isolated_cache)["accounts"][0]["videos"][0]["url"] == "stale"
