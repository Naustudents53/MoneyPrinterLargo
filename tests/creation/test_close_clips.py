"""
Tests for `YouTube._close_clips_safely` — the helper that releases
MoviePy file handles after combine() / combine_long(). It must:
  1. Call .close() on every clip.
  2. Not raise even if a clip's close() throws.
  3. Be safe with mixed types and None entries.
"""

from unittest.mock import MagicMock

from classes.YouTube import YouTube


def test_closes_all_clips():
    clips = [MagicMock() for _ in range(5)]
    YouTube._close_clips_safely(clips)
    for c in clips:
        c.close.assert_called_once()


def test_swallows_per_clip_errors():
    bad = MagicMock()
    bad.close.side_effect = RuntimeError("ffmpeg already gone")
    good = MagicMock()
    YouTube._close_clips_safely([bad, good])
    bad.close.assert_called_once()
    good.close.assert_called_once()  # second clip still closed despite first failure


def test_handles_empty_list():
    YouTube._close_clips_safely([])  # must not raise


def test_handles_clip_without_close_method():
    """Pathological case — something in the list isn't a clip."""
    not_a_clip = object()
    YouTube._close_clips_safely([not_a_clip])  # must not raise
