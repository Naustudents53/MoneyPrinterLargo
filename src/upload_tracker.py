"""
Tracks generated assets (video + images + audio + subtitles) per pipeline run
so that `rem_temp_files()` can distinguish between:

- Assets that already shipped to YouTube → safe to delete.
- Assets whose upload never started or failed → must be preserved so the
  user can retry from the "Re-upload existing video" menu without losing
  the (often expensive) generated images.

Mechanism: a sidecar manifest `<video_basename>.manifest.json` written next
to the rendered video in `.mp/`. The manifest is itself a `.json` file so
it survives the existing `rem_temp_files()` keep-list naturally.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Iterable

from config import ROOT_DIR

SUPPORTED_PLATFORMS = ("youtube", "tiktok", "facebook")


_MP_DIR = os.path.join(ROOT_DIR, ".mp")


def _manifest_path_for(video_path: str) -> str:
    base = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(_MP_DIR, f"{base}.manifest.json")


def _list_manifests() -> list[str]:
    if not os.path.isdir(_MP_DIR):
        return []
    return [
        os.path.join(_MP_DIR, f)
        for f in os.listdir(_MP_DIR)
        if f.endswith(".manifest.json")
    ]


def _read(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _normalize(paths: Iterable[str | None]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if not p:
            continue
        try:
            out.append(os.path.abspath(p))
        except Exception:
            continue
    return out


def record_generation(
    video_path: str,
    image_paths: Iterable[str],
    extra_paths: Iterable[str | None] = (),
    subject: str = "",
) -> str | None:
    """
    Persist a manifest listing every asset produced for this video so that
    cleanup logic can keep them alive until the video is confirmed uploaded.
    Returns the manifest path, or None if the video itself doesn't exist.
    """
    if not video_path or not os.path.isfile(video_path):
        return None

    manifest = {
        "video_path": os.path.abspath(video_path),
        "image_paths": _normalize(image_paths),
        "extra_paths": _normalize(extra_paths),
        "subject": subject or "",
        "uploaded": False,
        "uploaded_url": None,
        "platform_uploads": {
            platform: {"status": "pending", "url": None, "updated_at": None, "error": ""}
            for platform in SUPPORTED_PLATFORMS
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
        "uploaded_at": None,
    }
    path = _manifest_path_for(video_path)
    _write(path, manifest)
    return path


def mark_uploaded(video_path: str, url: str | None = None) -> bool:
    """Flip the manifest's uploaded flag. Returns True if a manifest was found."""
    if not video_path:
        return False
    path = _manifest_path_for(video_path)
    data = _read(path)
    if not data:
        return False
    data["uploaded"] = True
    data["uploaded_url"] = url or data.get("uploaded_url")
    data["uploaded_at"] = datetime.utcnow().isoformat() + "Z"
    platforms = data.setdefault("platform_uploads", {})
    platforms["youtube"] = {
        "status": "uploaded",
        "url": url or data.get("uploaded_url"),
        "updated_at": data["uploaded_at"],
        "error": "",
    }
    _write(path, data)
    return True


def mark_distribution_complete(video_path: str, url: str | None = None) -> bool:
    """Mark the generated asset safe to clean after selected platforms finished."""
    if not video_path:
        return False
    path = _manifest_path_for(video_path)
    data = _read(path)
    if not data:
        return False
    data["uploaded"] = True
    data["uploaded_url"] = url or data.get("uploaded_url")
    data["uploaded_at"] = datetime.utcnow().isoformat() + "Z"
    _write(path, data)
    return True


def mark_platform_uploaded(video_path: str, platform: str, url: str | None = None) -> bool:
    if platform not in SUPPORTED_PLATFORMS or not video_path:
        return False
    path = _manifest_path_for(video_path)
    data = _read(path)
    if not data:
        return False
    now = datetime.utcnow().isoformat() + "Z"
    platforms = data.setdefault("platform_uploads", {})
    platforms[platform] = {
        "status": "uploaded",
        "url": url,
        "updated_at": now,
        "error": "",
    }
    if platform == "youtube":
        data["uploaded_url"] = url or data.get("uploaded_url")
    _write(path, data)
    return True


def mark_platform_failed(video_path: str, platform: str, error: str = "") -> bool:
    if platform not in SUPPORTED_PLATFORMS or not video_path:
        return False
    path = _manifest_path_for(video_path)
    data = _read(path)
    if not data:
        return False
    platforms = data.setdefault("platform_uploads", {})
    platforms[platform] = {
        "status": "failed",
        "url": (platforms.get(platform) or {}).get("url"),
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "error": (error or "")[:300],
    }
    _write(path, data)
    return True


def is_uploaded(video_path: str) -> bool:
    data = _read(_manifest_path_for(video_path))
    return bool(data and data.get("uploaded"))


def pending_assets() -> set[str]:
    """
    Absolute paths of every asset belonging to a manifest whose upload has
    NOT been confirmed yet. `rem_temp_files()` consults this set to skip
    deletion of images/audio/subtitles that the user may still need.
    """
    protected: set[str] = set()
    for mpath in _list_manifests():
        data = _read(mpath)
        if not data or data.get("uploaded"):
            continue
        protected.add(os.path.abspath(mpath))
        for key in ("video_path", "image_paths", "extra_paths"):
            value = data.get(key)
            if isinstance(value, str):
                protected.add(os.path.abspath(value))
            elif isinstance(value, list):
                for p in value:
                    if isinstance(p, str) and p:
                        protected.add(os.path.abspath(p))
    return protected


def cleanup_uploaded() -> int:
    """
    Delete every asset belonging to manifests flagged as uploaded, then
    delete the manifests themselves. Returns the number of files removed.
    Best-effort: missing files are ignored.
    """
    removed = 0
    for mpath in _list_manifests():
        data = _read(mpath)
        if not data or not data.get("uploaded"):
            continue
        targets: list[str] = []
        for key in ("video_path", "image_paths", "extra_paths"):
            value = data.get(key)
            if isinstance(value, str):
                targets.append(value)
            elif isinstance(value, list):
                targets.extend(p for p in value if isinstance(p, str) and p)
        targets.append(mpath)
        for t in targets:
            try:
                if os.path.isfile(t):
                    os.remove(t)
                    removed += 1
            except Exception:
                pass
    return removed
