"""
Pluggable upload backend.

The legacy Selenium flow is one possible backend. The YouTube Data API
v3 (`videos.insert` with resumable upload) is another. Per-account
configuration (`upload_backend: "selenium" | "data_api"` in the cache
JSON) selects which one is used.

This module defines the interface and ships the Selenium implementation.
The Data API backend is a NotImplementedError skeleton — to enable it,
configure OAuth credentials and fill in `_perform_upload`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class UploadRequest:
    video_path: str
    metadata: dict
    subject: str
    thumbnail_path: str = ""
    is_long_video: bool = False
    visibility: str = "public"  # "public" | "unlisted" | "private"
    is_for_kids: bool = False
    on_cache_provisional: Optional[Callable[[dict], None]] = None
    on_cache_finalize: Optional[Callable[[str, str], None]] = None
    on_cache_interrupt: Optional[Callable[[str], None]] = None
    extra: dict = field(default_factory=dict)


@dataclass
class UploadOutcome:
    ok: bool
    url: Optional[str] = None
    interrupted: bool = False
    stage: str = ""
    screenshot_dir: Optional[str] = None


class UploadBackend(abc.ABC):
    """All backends share this surface so callers can swap them transparently."""

    name: str = "abstract"

    @abc.abstractmethod
    def upload(self, request: UploadRequest) -> UploadOutcome: ...

    def cleanup(self) -> None:  # optional
        return None


class SeleniumUploadBackend(UploadBackend):
    """
    Wraps `youtube_upload.upload_flow.UploadFlow`. Owns one BrowserSession
    bound to a Firefox profile path.
    """

    name = "selenium"

    def __init__(self, *, fp_profile_path: str, headless: bool = False, verbose: bool = True):
        from .browser_session import BrowserSession
        self._session = BrowserSession(
            fp_profile_path=fp_profile_path,
            headless=headless,
            verbose=verbose,
        )
        self._verbose = verbose

    def upload(self, request: UploadRequest) -> UploadOutcome:
        from .upload_flow import UploadFlow

        flow = UploadFlow(
            self._session,
            is_for_kids=request.is_for_kids,
            verbose=self._verbose,
            on_cache_provisional=request.on_cache_provisional,
            on_cache_finalize=request.on_cache_finalize,
            on_cache_interrupt=request.on_cache_interrupt,
        )
        result = flow.upload(
            video_path=request.video_path,
            metadata=request.metadata,
            subject=request.subject,
            thumbnail_path=request.thumbnail_path,
            is_long_video=request.is_long_video,
            visibility=request.visibility,
        )
        return UploadOutcome(
            ok=result.ok,
            url=result.url,
            interrupted=result.interrupted,
            stage=result.stage,
            screenshot_dir=result.screenshot_dir,
        )

    def cleanup(self) -> None:
        try:
            self._session.cleanup()
        except Exception:
            pass

    @property
    def session(self):
        """Exposed so legacy callers (`YouTubeUploader`) can attach a
        driver reference for backward-compat methods that are still
        expected to read `self.browser`."""
        return self._session


class YouTubeDataApiBackend(UploadBackend):
    """
    Skeleton for the YouTube Data API v3 backend. To implement:

    1. Add OAuth credentials to the account cache JSON
       (refresh_token + client_id + client_secret).
    2. Use `google-api-python-client` to call `youtube.videos().insert(
           part="snippet,status",
           body={...}, media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
       )`.
    3. After insert succeeds, optionally call `youtube.thumbnails().set(
           videoId=..., media_body=MediaFileUpload(thumb_path)
       )`.
    4. Construct the public URL via `utils.build_url(video_id)`.

    Until that's wired, this backend raises `NotImplementedError` so the
    user sees an explicit error if they configure `upload_backend="data_api"`
    on an account that doesn't have credentials yet.
    """

    name = "data_api"

    def __init__(self, *, account: dict):
        self._account = account

    def upload(self, request: UploadRequest) -> UploadOutcome:
        raise NotImplementedError(
            "YouTubeDataApiBackend is a skeleton. To enable it: configure "
            "OAuth credentials on the account JSON, install "
            "`google-api-python-client`, and implement `_perform_upload`."
        )


def build_backend(*, account: dict, headless: bool, verbose: bool) -> UploadBackend:
    """
    Factory: pick the backend based on `account["upload_backend"]`.
    Defaults to `"selenium"` for backward compat.
    """
    backend_name = (account.get("upload_backend") or "selenium").strip().lower()
    if backend_name == "data_api":
        return YouTubeDataApiBackend(account=account)
    return SeleniumUploadBackend(
        fp_profile_path=account.get("firefox_profile") or "",
        headless=headless,
        verbose=verbose,
    )
