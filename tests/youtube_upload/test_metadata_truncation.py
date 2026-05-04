"""
Tests for `UploadFlow._truncate_metadata`. Verifies F1.4 + F1.5:
- Title: replace newlines with spaces, cap at title_max_chars, warn if truncated.
- Description: preserve newlines, cap at description_max_chars.
- Mutates the dict in place so sidecar saves the truncated version.
"""

from unittest.mock import MagicMock

from youtube_upload.upload_flow import UploadFlow


def _flow():
    """Construct an UploadFlow with a mock session for unit testing
    helpers that don't touch Selenium."""
    fake_session = MagicMock()
    return UploadFlow(fake_session, verbose=False)


def test_truncates_long_title():
    flow = _flow()
    md = {"title": "a" * 200, "description": "ok"}
    flow._truncate_metadata(md)
    assert len(md["title"]) == 100
    assert md["title"] == "a" * 100


def test_strips_newlines_from_title():
    flow = _flow()
    md = {"title": "Line 1\nLine 2\nLine 3", "description": "ok"}
    flow._truncate_metadata(md)
    assert "\n" not in md["title"]
    assert md["title"] == "Line 1 Line 2 Line 3"


def test_short_title_unchanged():
    flow = _flow()
    md = {"title": "Short title", "description": "ok"}
    flow._truncate_metadata(md)
    assert md["title"] == "Short title"


def test_preserves_description_newlines():
    """F1.5: description must keep newlines (YouTube accepts multi-line)."""
    flow = _flow()
    md = {"title": "ok", "description": "Para 1.\n\nPara 2.\n\nPara 3."}
    flow._truncate_metadata(md)
    assert md["description"] == "Para 1.\n\nPara 2.\n\nPara 3."
    assert md["description"].count("\n") == 4


def test_truncates_long_description_keeps_prefix():
    flow = _flow()
    desc = ("paragraph one.\n\n" + ("x" * 6000))
    md = {"title": "ok", "description": desc}
    flow._truncate_metadata(md)
    assert len(md["description"]) == 5000
    assert md["description"].startswith("paragraph one.\n\n")


def test_handles_missing_keys():
    flow = _flow()
    md = {}
    flow._truncate_metadata(md)
    assert md["title"] == ""
    assert md["description"] == ""
