"""
Tests for `youtube_upload.failure_capture.capture` and `purge_old`.
We use a fake driver double instead of pulling in Selenium.
"""

import os
import time
from unittest.mock import patch

import pytest


class FakeDriver:
    """Minimal stand-in for selenium.webdriver.Firefox."""

    def __init__(self, *, fail_screenshot=False, fail_source=False):
        self.fail_screenshot = fail_screenshot
        self.fail_source = fail_source
        self.current_url = "https://studio.youtube.com/channel/UC123/videos/short"
        self._screenshot_path: str | None = None

    def save_screenshot(self, path: str) -> bool:
        if self.fail_screenshot:
            raise RuntimeError("driver dead")
        with open(path, "wb") as f:
            f.write(b"FAKE_PNG")
        self._screenshot_path = path
        return True

    @property
    def page_source(self) -> str:
        if self.fail_source:
            raise RuntimeError("source unavailable")
        return "<html><body>fake</body></html>"


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Redirect ROOT_DIR so we don't pollute the real .mp folder."""
    root = tmp_path / "fake_root"
    root.mkdir()
    monkeypatch.setattr("youtube_upload.failure_capture.ROOT_DIR", str(root))
    return str(root)


def test_capture_creates_folder_with_screenshot_and_source(isolated_root):
    from youtube_upload.failure_capture import capture

    driver = FakeDriver()
    folder = capture(driver, "thumbnail_failed", extra={"path": "/tmp/x.png"})
    assert folder is not None
    assert os.path.isdir(folder)
    assert os.path.isfile(os.path.join(folder, "screenshot.png"))
    assert os.path.isfile(os.path.join(folder, "page.html"))
    assert os.path.isfile(os.path.join(folder, "context.txt"))

    with open(os.path.join(folder, "context.txt"), encoding="utf-8") as f:
        ctx = f.read()
    assert "thumbnail_failed" in ctx
    assert "/tmp/x.png" in ctx
    assert "studio.youtube.com" in ctx


def test_capture_survives_screenshot_failure(isolated_root):
    from youtube_upload.failure_capture import capture

    driver = FakeDriver(fail_screenshot=True)
    folder = capture(driver, "boom")
    assert folder is not None
    # Screenshot file shouldn't exist; page.html should.
    assert not os.path.isfile(os.path.join(folder, "screenshot.png"))
    assert os.path.isfile(os.path.join(folder, "page.html"))


def test_capture_returns_none_for_none_driver(isolated_root):
    from youtube_upload.failure_capture import capture
    assert capture(None, "x") is None


def test_purge_old_removes_aged_folders(isolated_root):
    from youtube_upload.failure_capture import capture, purge_old

    driver = FakeDriver()
    folder = capture(driver, "old_one")
    assert folder

    # Backdate the folder to >7 days ago
    old_time = time.time() - 8 * 86400
    os.utime(folder, (old_time, old_time))

    # Fresh folder
    fresh = capture(driver, "fresh_one")

    removed = purge_old(retention_days=7)
    assert removed >= 1
    assert not os.path.isdir(folder)
    assert os.path.isdir(fresh)


def test_slug_handles_dirty_input(isolated_root):
    from youtube_upload.failure_capture import _slug
    assert _slug("hello world!") == "hello_world"
    assert _slug("") == "fail"
    assert _slug("   ") == "fail"
    assert _slug("a/b/c") == "a_b_c"
    # Length cap
    assert len(_slug("x" * 200)) <= 60
