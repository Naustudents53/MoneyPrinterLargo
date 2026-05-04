"""
Tests for `YouTube.add_video` and `YouTube.get_videos`.

The legacy add_video had dead code (it called get_videos() and mutated
the returned list, which immediately went out of scope) AND it
re-opened the cache to do the actual append. The cleanup must:
  - Append the video exactly once.
  - Be atomic (use write_atomic).
  - Handle a freshly-created cache (correct shape, no KeyError).
  - Be a no-op for unknown account IDs (no crash).
"""

import json
import os
import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    cache_path = tmp_path / "youtube.json"
    monkeypatch.setattr(
        "classes.YouTube.get_youtube_cache_path",
        lambda: str(cache_path),
    )
    return str(cache_path)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _make_youtube_for_test(account_id: str = "acc-1"):
    """Bypass the heavy __init__ (which fires up Selenium) by creating
    a bare instance and only setting the attributes get_videos /
    add_video need."""
    from classes.YouTube import YouTube
    obj = YouTube.__new__(YouTube)
    obj._account_uuid = account_id
    return obj


def test_add_video_appends_exactly_once(isolated_cache):
    # Seed cache with the account but no videos
    with open(isolated_cache, "w", encoding="utf-8") as f:
        json.dump({"accounts": [{"id": "acc-1", "videos": []}]}, f)

    yt = _make_youtube_for_test("acc-1")
    yt.add_video({"title": "first", "url": "u"})

    data = _read(isolated_cache)
    videos = data["accounts"][0]["videos"]
    assert len(videos) == 1
    assert videos[0]["title"] == "first"


def test_add_video_works_when_cache_missing(isolated_cache):
    yt = _make_youtube_for_test("acc-1")
    # Cache missing — get_videos creates it
    yt.get_videos()
    yt.add_video({"title": "first"})
    # No crash, but the video can't be persisted because the account
    # doesn't exist yet in the cache. add_video is a no-op for unknown
    # accounts (the user must add the account first via add_account).
    data = _read(isolated_cache)
    assert data == {"accounts": []}


def test_get_videos_creates_correct_shape(isolated_cache):
    yt = _make_youtube_for_test("acc-1")
    assert yt.get_videos() == []
    # Cache file should have the proper accounts shape (NOT the buggy
    # legacy {"videos": []} that breaks the next read with KeyError).
    data = _read(isolated_cache)
    assert "accounts" in data
    assert data["accounts"] == []


def test_get_videos_returns_only_this_account(isolated_cache):
    with open(isolated_cache, "w", encoding="utf-8") as f:
        json.dump({"accounts": [
            {"id": "acc-1", "videos": [{"t": "a"}, {"t": "b"}]},
            {"id": "acc-2", "videos": [{"t": "x"}]},
        ]}, f)

    yt = _make_youtube_for_test("acc-1")
    videos = yt.get_videos()
    assert len(videos) == 2
    assert videos[0]["t"] == "a"


def test_add_video_writes_atomically(isolated_cache):
    """write_atomic should leave no .tmp siblings."""
    with open(isolated_cache, "w", encoding="utf-8") as f:
        json.dump({"accounts": [{"id": "acc-1", "videos": []}]}, f)

    yt = _make_youtube_for_test("acc-1")
    yt.add_video({"title": "x"})

    cache_dir = os.path.dirname(isolated_cache)
    leftovers = [
        n for n in os.listdir(cache_dir)
        if n != os.path.basename(isolated_cache)
    ]
    assert leftovers == []


def test_add_video_three_calls_yields_three_entries(isolated_cache):
    """Regression for the legacy double-write: each add_video call
    must add exactly one entry, never two."""
    with open(isolated_cache, "w", encoding="utf-8") as f:
        json.dump({"accounts": [{"id": "acc-1", "videos": []}]}, f)

    yt = _make_youtube_for_test("acc-1")
    yt.add_video({"title": "v1"})
    yt.add_video({"title": "v2"})
    yt.add_video({"title": "v3"})

    videos = _read(isolated_cache)["accounts"][0]["videos"]
    assert [v["title"] for v in videos] == ["v1", "v2", "v3"]
