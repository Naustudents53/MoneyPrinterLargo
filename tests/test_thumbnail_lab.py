import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

pytest.importorskip("PIL")
pytest.importorskip("numpy")

from PIL import Image, ImageDraw

from classes import ThumbnailLab as tl


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _flat_gray() -> bytes:
    return _png_bytes(Image.new("RGB", (640, 360), (128, 128, 128)))


def _dark_mud() -> bytes:
    return _png_bytes(Image.new("RGB", (640, 360), (18, 14, 20)))


def _vibrant_subject() -> bytes:
    """High-contrast colorful image with one dominant central subject."""
    img = Image.new("RGB", (640, 360), (20, 30, 60))
    draw = ImageDraw.Draw(img)
    # Bright warm focal subject in the center region.
    draw.ellipse((220, 90, 420, 270), fill=(250, 160, 30))
    draw.ellipse((270, 130, 370, 230), fill=(255, 230, 120))
    # Some secondary detail so contrast/color stats are realistic.
    draw.rectangle((0, 300, 640, 360), fill=(60, 20, 90))
    return _png_bytes(img)


def test_flat_image_scores_low_with_issue():
    result = tl.score_thumbnail_image(_flat_gray())
    assert result["score"] < tl.SCORE_THRESHOLD
    assert any("contrast" in issue for issue in result["issues"])


def test_dark_image_flagged():
    result = tl.score_thumbnail_image(_dark_mud())
    assert any("dark" in issue for issue in result["issues"])


def test_vibrant_subject_beats_flat_and_dark():
    vibrant = tl.score_thumbnail_image(_vibrant_subject())
    flat = tl.score_thumbnail_image(_flat_gray())
    dark = tl.score_thumbnail_image(_dark_mud())
    assert vibrant["score"] > flat["score"]
    assert vibrant["score"] > dark["score"]


def test_select_best_background_picks_vibrant():
    candidates = [_flat_gray(), _vibrant_subject(), _dark_mud()]
    idx, report = tl.select_best_background(candidates)
    assert idx == 1
    assert report["best_index"] == 1
    assert report["candidate_count"] == 3
    assert len(report["candidates"]) == 3


def test_select_best_background_survives_undecodable_candidate():
    candidates = [b"not-an-image", _vibrant_subject()]
    idx, report = tl.select_best_background(candidates)
    assert idx == 1
    assert report["candidates"][0]["score"] == 0.0


def test_select_best_background_rejects_empty_list():
    with pytest.raises(ValueError):
        tl.select_best_background([])
