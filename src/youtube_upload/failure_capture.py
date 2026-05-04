"""
Persist debug evidence (screenshot + page source) when an upload step
fails. Files land in `.mp/upload_failures/<ts>__<reason>/`.

Old failure folders are purged after FAILURE_RETENTION_DAYS so this
directory does not grow unbounded.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from datetime import datetime, timedelta

from config import ROOT_DIR


FAILURE_RETENTION_DAYS = 7


def _failure_root() -> str:
    path = os.path.join(ROOT_DIR, ".mp", "upload_failures")
    os.makedirs(path, exist_ok=True)
    return path


def _slug(reason: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (reason or "fail")).strip("_")[:60] or "fail"


def capture(driver, reason: str, *, extra: dict | None = None) -> str | None:
    """
    Save a screenshot + raw page source to a fresh folder under
    `.mp/upload_failures/`. Returns the folder path on success, None on
    failure (capture itself never raises — callers must not rely on it).
    """
    if driver is None:
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(_failure_root(), f"{ts}__{_slug(reason)}")
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        return None

    try:
        driver.save_screenshot(os.path.join(folder, "screenshot.png"))
    except Exception:
        pass

    try:
        with open(os.path.join(folder, "page.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
    except Exception:
        pass

    try:
        url = driver.current_url
    except Exception:
        url = ""

    try:
        with open(os.path.join(folder, "context.txt"), "w", encoding="utf-8") as f:
            f.write(f"reason: {reason}\n")
            f.write(f"timestamp: {ts}\n")
            f.write(f"url: {url}\n")
            if extra:
                for k, v in extra.items():
                    f.write(f"{k}: {v}\n")
    except Exception:
        pass

    return folder


def purge_old(retention_days: int = FAILURE_RETENTION_DAYS) -> int:
    """Delete failure folders older than retention_days. Returns count
    of folders removed. Never raises."""
    root = _failure_root()
    cutoff = time.time() - retention_days * 86400
    removed = 0
    try:
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if not os.path.isdir(path):
                continue
            try:
                if os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except Exception:
                continue
    except FileNotFoundError:
        return 0
    except Exception:
        return removed
    return removed
