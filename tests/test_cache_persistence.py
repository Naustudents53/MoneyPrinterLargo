import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import cache


def test_atomic_write_json_replaces_content_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "data.json"
    target.write_text('{"old": true}', encoding="utf-8")

    cache.atomic_write_json(str(target), {"accounts": [{"id": "a"}]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"accounts": [{"id": "a"}]}
    assert not os.path.exists(str(target) + ".tmp")


def test_get_products_survives_corrupt_and_malformed_files(tmp_path, monkeypatch):
    afm = tmp_path / "afm.json"
    monkeypatch.setattr(cache, "get_afm_cache_path", lambda: str(afm))

    # Missing file -> created with the right shape, returns [].
    assert cache.get_products() == []
    assert json.loads(afm.read_text(encoding="utf-8")) == {"products": []}

    # Truncated/corrupt JSON (e.g. crash mid-write before the atomic fix).
    afm.write_text('{"products": [{"name": "x"', encoding="utf-8")
    assert cache.get_products() == []

    # Wrong shapes must not raise.
    afm.write_text("null", encoding="utf-8")
    assert cache.get_products() == []
    afm.write_text('{"otra_clave": 1}', encoding="utf-8")
    assert cache.get_products() == []


def test_add_product_appends_atomically(tmp_path, monkeypatch):
    afm = tmp_path / "afm.json"
    monkeypatch.setattr(cache, "get_afm_cache_path", lambda: str(afm))

    cache.add_product({"name": "uno"})
    cache.add_product({"name": "dos"})

    data = json.loads(afm.read_text(encoding="utf-8"))
    assert [p["name"] for p in data["products"]] == ["uno", "dos"]
    assert not os.path.exists(str(afm) + ".tmp")
    assert not os.path.exists(str(afm) + ".lock")


def test_get_videos_creates_accounts_shape_not_videos_shape(tmp_path, monkeypatch):
    """The old code seeded {"videos": []}, so the very next read crashed with
    KeyError("accounts"). The seed must match what every reader expects."""
    import classes.YouTube as yt_mod

    yt_cache = tmp_path / "youtube.json"
    monkeypatch.setattr(yt_mod, "get_youtube_cache_path", lambda: str(yt_cache))

    youtube = yt_mod.YouTube.__new__(yt_mod.YouTube)
    youtube._account_uuid = "acc-1"

    assert youtube.get_videos() == []
    assert json.loads(yt_cache.read_text(encoding="utf-8")) == {"accounts": []}
    # Second call reads the file it just created — must not raise.
    assert youtube.get_videos() == []
