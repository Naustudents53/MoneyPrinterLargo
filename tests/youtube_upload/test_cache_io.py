"""
Tests for `youtube_upload.cache_io` — atomic JSON read/write.

The legacy code did `open(path, 'w') + json.dump`. If killed mid-write
the cache file became invalid JSON. write_atomic must:
  1. Replace the file atomically (either old version OR new one).
  2. Never leave a half-written file.
  3. Roundtrip JSON unchanged (Unicode preserved, indent honored).
"""

import json
import os

import pytest

from youtube_upload.cache_io import read_json, write_atomic


def test_write_atomic_roundtrip(tmp_path):
    path = str(tmp_path / "cache.json")
    data = {"accounts": [{"id": "abc", "videos": []}]}
    write_atomic(path, data)
    assert read_json(path) == data


def test_write_atomic_overwrite(tmp_path):
    path = str(tmp_path / "cache.json")
    write_atomic(path, {"v": 1})
    write_atomic(path, {"v": 2})
    assert read_json(path) == {"v": 2}


def test_write_atomic_preserves_unicode(tmp_path):
    path = str(tmp_path / "cache.json")
    data = {"title": "El renacimiento — siglo XV ✨"}
    write_atomic(path, data)
    # Read raw to verify it's not escape-encoded
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert "renacimiento" in raw
    assert "—" in raw
    assert "\\u" not in raw  # no \uXXXX escapes


def test_write_atomic_does_not_leak_tempfiles(tmp_path):
    path = str(tmp_path / "cache.json")
    write_atomic(path, {"x": 1})
    write_atomic(path, {"x": 2})
    # Only the target file should remain — no .tmp siblings
    leftovers = [
        n for n in os.listdir(tmp_path)
        if n != "cache.json"
    ]
    assert leftovers == []


def test_read_json_returns_default_when_missing(tmp_path):
    path = str(tmp_path / "missing.json")
    assert read_json(path) == {}
    assert read_json(path, default=[]) == []
    assert read_json(path, default={"accounts": []}) == {"accounts": []}


def test_read_json_returns_default_when_corrupt(tmp_path):
    path = str(tmp_path / "broken.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert read_json(path, default={"accounts": []}) == {"accounts": []}


def test_write_atomic_does_not_clobber_on_failure(tmp_path, monkeypatch):
    """Simulate an exception during write — original file should survive."""
    path = str(tmp_path / "cache.json")
    write_atomic(path, {"original": True})

    # Patch os.replace to raise so the rename never happens
    import youtube_upload.cache_io as mod
    real_replace = mod.os.replace

    def boom(*args, **kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(mod.os, "replace", boom)
    with pytest.raises(OSError):
        write_atomic(path, {"new": True})

    # Restore for cleanup checks
    monkeypatch.setattr(mod.os, "replace", real_replace)

    # Original file unchanged
    assert read_json(path) == {"original": True}
    # And no tempfile leak
    leftovers = [n for n in os.listdir(tmp_path) if n != "cache.json"]
    assert leftovers == []
