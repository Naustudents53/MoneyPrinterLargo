"""
Tests for the URL extraction helpers used by StudioListingPoller.
We don't spin up a driver — just verify that given a row's `<a href>`
shape, we extract the right video id and build the canonical URL.
"""

from utils import build_url


def test_build_url_returns_canonical_form():
    assert build_url("dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_video_id_extraction_from_studio_href():
    """Studio shows a row href like
    `https://studio.youtube.com/video/<VIDEO_ID>/edit` — we grab the
    second-to-last path segment."""
    href = "https://studio.youtube.com/video/dQw4w9WgXcQ/edit"
    video_id = href.split("/")[-2]
    assert video_id == "dQw4w9WgXcQ"
    assert build_url(video_id) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
