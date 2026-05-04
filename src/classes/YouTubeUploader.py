"""
Backward-compatible facade.

Historically `YouTubeUploader` was a 900-line class that `YouTube`
inherits from. The actual logic now lives in `src/youtube_upload/`
(BrowserSession + UploadFlow + StudioListingPoller + ThumbnailUploader),
but this shim preserves the inheritance contract so the rest of the
codebase doesn't need to change.

What `YouTube` (and its subclasses, e.g. MovieSummary) still rely on:

    self._init_selenium(fp_profile_path)   # called from YouTube.__init__
    self._ensure_browser()
    self.browser                           # the live driver
    self.get_channel_id()
    self.upload_video()                    # the big public method
    self._update_last_video_url(...)       # cache patch
    self._is_long_video                    # flag set by long-video pipeline

All of the above are delegated to the new package. The only behavior
that changes is robustness (Ctrl+A title clearing, explicit waits,
failure capture, KeyboardInterrupt handling, tempdir cleanup) — wire
shape stays the same.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from cache import get_youtube_cache_path
from config import get_headless, get_imagemagick_path, get_is_for_kids, get_verbose
from moviepy.config import change_settings
from status import error, info, success, warning

from youtube_upload import upload_config
from youtube_upload.browser_session import BrowserSession
from youtube_upload.cache_io import read_json, write_atomic
from youtube_upload.failure_capture import purge_old as purge_old_failures
from youtube_upload.listing_poller import StudioListingPoller
from youtube_upload.upload_flow import UploadFlow


change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTubeUploader:
    """Mixin used by `YouTube` (and `MovieSummary`) for the upload step."""

    # ============================================================
    #  Browser lifecycle (legacy method names preserved)
    # ============================================================

    def _init_selenium(self, fp_profile_path: str) -> None:
        self._session = BrowserSession(
            fp_profile_path=fp_profile_path,
            headless=get_headless(),
            verbose=get_verbose(),
        )
        # Legacy alias — older code reads `self.browser` directly.
        self.browser = None
        # Garbage-collect old failure folders once per process.
        try:
            purge_old_failures()
        except Exception:
            pass

    def _ensure_browser(self):
        self.browser = self._session.ensure_alive()
        return self.browser

    def cleanup(self) -> None:
        """Quit the driver and delete the cloned Firefox profile.
        Always safe to call multiple times."""
        try:
            self._session.cleanup()
        except Exception:
            pass
        self.browser = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    # ============================================================
    #  Channel ID  (legacy public method)
    # ============================================================

    def get_channel_id(self) -> str:
        self._ensure_browser()
        from selenium.common.exceptions import TimeoutException, WebDriverException

        attempts = 2
        last_err: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                self.browser.get("https://studio.youtube.com")
                # Brief settle so the SPA redirects to /channel/<id>.
                import time
                time.sleep(2)
                channel_id = self.browser.current_url.split("/")[-1]
                self.channel_id = channel_id
                return channel_id
            except (WebDriverException, TimeoutException) as e:
                last_err = e
                if attempt < attempts:
                    warning(
                        f"Navigation to YouTube Studio failed "
                        f"({type(e).__name__}: {str(e)[:120]}). Retrying with a fresh browser..."
                    )
                    self.cleanup()
                    self._ensure_browser()
                    continue
                raise
        if last_err:
            raise last_err
        return ""

    # ============================================================
    #  Public upload entry point
    # ============================================================

    def upload_video(self) -> bool:
        """
        Run the full upload flow for the currently-rendered video.

        Reads from `self`:
          - video_path, subject, metadata (title/description), thumbnail_path
          - _is_long_video flag (set by long pipeline)
          - _account_uuid (used by the cache patcher)

        Side effects: writes a provisional cache entry, polls Studio,
        patches the cache with the public URL, and may close the
        browser on a clean Short upload (long videos always leave it
        open).

        Returns True on success, False otherwise.
        """
        self._ensure_browser()

        is_long_video = bool(getattr(self, "_is_long_video", False))
        thumbnail_path = getattr(self, "thumbnail_path", "") or ""
        metadata = dict(getattr(self, "metadata", {}) or {})
        subject = getattr(self, "subject", "") or ""

        flow = UploadFlow(
            self._session,
            is_for_kids=get_is_for_kids(),
            verbose=get_verbose(),
            on_cache_provisional=self._cache_provisional,
            on_cache_finalize=self._cache_finalize,
            on_cache_interrupt=self._cache_interrupt,
        )
        result = flow.upload(
            video_path=getattr(self, "video_path", "") or "",
            metadata=metadata,
            subject=subject,
            thumbnail_path=thumbnail_path,
            is_long_video=is_long_video,
            visibility="public",
        )

        # Reflect post-truncation metadata back onto self so a sidecar
        # written *after* upload matches what YT actually received.
        if metadata:
            self.metadata = metadata

        if result.url:
            self.uploaded_video_url = result.url
        else:
            self.uploaded_video_url = "https://studio.youtube.com"

        # On clean Short upload the flow closed the browser itself;
        # reflect that in our legacy reference.
        if self._session.driver is None:
            self.browser = None

        return bool(result.ok)

    # ============================================================
    #  Cache callbacks (used by UploadFlow)
    # ============================================================

    def _cache_provisional(self, entry: dict) -> None:
        try:
            self.add_video(entry)
            if get_verbose():
                info("\t=> Cache entry saved (with placeholder URL)")
        except Exception as e:
            warning(f"Could not pre-save cache entry: {e}")

    def _cache_finalize(self, date_marker: str, new_url: str) -> None:
        self._update_last_video_url(date_marker, new_url)

    def _cache_interrupt(self, date_marker: str) -> None:
        self._mark_cache_entry(date_marker, status="interrupted")

    # ============================================================
    #  Cache patchers (legacy — kept for backward compat)
    # ============================================================

    def _update_last_video_url(self, date_marker: str, new_url: str) -> None:
        cache = get_youtube_cache_path()
        data = read_json(cache, default=None)
        if data is None:
            return
        for account in data.get("accounts", []):
            if account.get("id") != getattr(self, "_account_uuid", None):
                continue
            for video in account.get("videos", []):
                if (
                    video.get("date") == date_marker
                    and video.get("url") in ("uploading...", "", None)
                ):
                    video["url"] = new_url
                    video["last_seen_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break
        write_atomic(cache, data)

    def _mark_cache_entry(self, date_marker: str, *, status: str) -> None:
        """Mark an in-flight cache entry with a terminal status string
        (e.g. "interrupted", "stale"). Doesn't touch entries that
        already have a real URL."""
        cache = get_youtube_cache_path()
        data = read_json(cache, default=None)
        if data is None:
            return
        for account in data.get("accounts", []):
            if account.get("id") != getattr(self, "_account_uuid", None):
                continue
            for video in account.get("videos", []):
                if video.get("date") == date_marker and video.get("url") in ("uploading...", "", None):
                    video["url"] = status
                    video["last_seen_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    break
        write_atomic(cache, data)


# ---------------------------------------------------------------------------
# Module-level helper used by main.py at startup.
# ---------------------------------------------------------------------------


def reconcile_pending_uploads() -> int:
    """
    Mark every `url == "uploading..."` cache entry older than the
    configured grace window (`youtube_upload.stale_uploading_hours`) as
    `"stale"`. Returns the count of entries patched.

    Should be called once on app startup so cache doesn't accumulate
    forever-pending placeholders left by crashed runs.
    """
    cache = get_youtube_cache_path()
    if not os.path.isfile(cache):
        return 0
    data = read_json(cache, default=None)
    if data is None:
        return 0

    grace = timedelta(hours=upload_config.stale_uploading_hours())
    cutoff = datetime.now() - grace
    patched = 0

    for account in data.get("accounts", []):
        for video in account.get("videos", []):
            if video.get("url") != "uploading...":
                continue
            stamp = video.get("last_seen_at") or video.get("date") or ""
            try:
                ts = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = None
            if ts is None or ts < cutoff:
                video["url"] = "stale"
                patched += 1

    if patched:
        write_atomic(cache, data)

    return patched
