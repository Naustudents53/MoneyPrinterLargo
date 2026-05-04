"""
Atomic JSON read/write for the YouTube cache files.

The legacy code does `open(path, "w") + json.dump`, which leaves the
file partially written if the process is killed mid-render. Replace
with `write_atomic` (write to tempfile + os.replace) so the cache file
is either the old version or the new one — never a half-truth.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def read_json(path: str, default: Any = None) -> Any:
    """Load JSON, returning `default` if the file is missing or unreadable."""
    if not os.path.isfile(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_atomic(path: str, data: Any, *, indent: int = 4) -> None:
    """
    Atomically replace the file at `path` with JSON-serialized `data`.

    Implementation: write to a sibling tempfile in the same directory
    (so os.replace is atomic on POSIX *and* on Windows), then rename.
    On crash, the original file survives untouched.
    """
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(target_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=".",
        suffix=".tmp",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup if write fails; never leak tempfiles.
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise
