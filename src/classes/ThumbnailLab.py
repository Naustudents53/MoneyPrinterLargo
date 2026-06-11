"""ThumbnailLab: deterministic CTR scoring for thumbnail backgrounds.

The thumbnail is half of long-form CTR (the other half is the title, already
covered by LongPackaging's title lab). This module scores candidate background
images with cheap, deterministic heuristics — no vision LLM — so the pipeline
can render N candidates and keep the one most likely to read well in the feed:

  - contrast: flat, washed-out images don't pop against YouTube's UI.
  - brightness: too dark or blown-out kills detail at feed size.
  - colorfulness: saturated images outperform gray ones in browse.
  - subject dominance: one clear focal region beats uniform texture. Proxied
    by center-region detail vs border detail.
  - clutter: too much edge detail everywhere reads as noise at 120px wide.
  - small-size legibility: the same contrast check at actual feed size.

PIL + numpy only (both already required by the render pipeline).
"""

from __future__ import annotations

import io
from typing import Any

SCORE_THRESHOLD = 6.0
FEED_SIZE = (120, 68)  # roughly what a browse-feed thumbnail occupies

_BRIGHTNESS_LOW = 50.0
_BRIGHTNESS_HIGH = 200.0
_CONTRAST_GOOD = 55.0
_CONTRAST_FLAT = 28.0
_COLORFULNESS_GOOD = 35.0
_COLORFULNESS_GRAY = 12.0
_CLUTTER_HIGH = 26.0
_SUBJECT_RATIO_GOOD = 1.25


def _to_arrays(image_bytes: bytes):
    """Decode to (rgb float array, grayscale float array), downscaled for speed."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Work at a bounded size: heuristics are scale-invariant enough and this
    # keeps scoring instant even for 4K candidates.
    img.thumbnail((640, 640), Image.LANCZOS)
    rgb = np.asarray(img, dtype=np.float32)
    gray = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return img, rgb, gray


def _colorfulness(rgb) -> float:
    """Hasler & Süsstrunk colorfulness metric."""
    import numpy as np

    rg = rgb[..., 0] - rgb[..., 1]
    yb = 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    return float(
        np.sqrt(rg.std() ** 2 + yb.std() ** 2)
        + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )


def _edge_density(gray) -> float:
    """Mean gradient magnitude — a clutter proxy."""
    import numpy as np

    gy, gx = np.gradient(gray)
    return float(np.sqrt(gx**2 + gy**2).mean())


def _subject_dominance(gray) -> float:
    """Detail in the center region relative to the borders.

    A strong single subject concentrates detail near the (rule-of-thirds)
    center; uniform texture or empty centers score ~1.0 or below.
    """
    import numpy as np

    h, w = gray.shape
    cy0, cy1 = int(h * 0.22), int(h * 0.78)
    cx0, cx1 = int(w * 0.22), int(w * 0.78)
    center = gray[cy0:cy1, cx0:cx1]
    mask = np.ones_like(gray, dtype=bool)
    mask[cy0:cy1, cx0:cx1] = False
    border = gray[mask]
    center_detail = float(center.std())
    border_detail = float(border.std()) or 1.0
    return center_detail / border_detail


def score_thumbnail_image(image_bytes: bytes) -> dict[str, Any]:
    """Score one candidate background. Returns {score, metrics, issues}.

    Score is 0-10; >= SCORE_THRESHOLD reads as "will pop in the feed".
    """
    import numpy as np

    img, rgb, gray = _to_arrays(image_bytes)

    brightness = float(gray.mean())
    contrast = float(gray.std())
    colorfulness = _colorfulness(rgb)
    clutter = _edge_density(gray)
    dominance = _subject_dominance(gray)

    # Legibility at feed size: shrink to ~120px and re-measure contrast.
    from PIL import Image

    small = img.resize(FEED_SIZE, Image.LANCZOS)
    small_gray = np.asarray(small.convert("L"), dtype=np.float32)
    feed_contrast = float(small_gray.std())

    score = 5.0
    issues: list[str] = []

    if contrast >= _CONTRAST_GOOD:
        score += 1.5
    elif contrast < _CONTRAST_FLAT:
        score -= 2.0
        issues.append("flat/washed-out image (low contrast)")

    if brightness < _BRIGHTNESS_LOW:
        score -= 1.5
        issues.append("too dark for feed visibility")
    elif brightness > _BRIGHTNESS_HIGH:
        score -= 1.0
        issues.append("blown-out highlights")
    else:
        score += 0.5

    if colorfulness >= _COLORFULNESS_GOOD:
        score += 1.5
    elif colorfulness < _COLORFULNESS_GRAY:
        score -= 1.5
        issues.append("near-grayscale image")

    if dominance >= _SUBJECT_RATIO_GOOD:
        score += 1.5
    elif dominance < 0.85:
        score -= 1.0
        issues.append("no clear focal subject in the center region")

    if clutter > _CLUTTER_HIGH:
        score -= 1.5
        issues.append("cluttered: too much fine detail to read at feed size")

    if feed_contrast < _CONTRAST_FLAT:
        score -= 1.0
        issues.append("loses contrast at feed size")
    elif feed_contrast >= _CONTRAST_GOOD:
        score += 0.5

    score = max(0.0, min(10.0, score))
    return {
        "score": round(score, 2),
        "metrics": {
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "colorfulness": round(colorfulness, 1),
            "clutter": round(clutter, 1),
            "subject_dominance": round(dominance, 2),
            "feed_contrast": round(feed_contrast, 1),
        },
        "issues": issues,
    }


def select_best_background(candidates: list[bytes]) -> tuple[int, dict[str, Any]]:
    """Score every candidate and return (best_index, report).

    Candidates that fail to decode are skipped (score 0). Always returns a
    valid index into `candidates` as long as the list is non-empty.
    """
    if not candidates:
        raise ValueError("no thumbnail candidates to score")

    scored: list[dict[str, Any]] = []
    for idx, data in enumerate(candidates):
        try:
            result = score_thumbnail_image(data)
        except Exception as exc:
            result = {"score": 0.0, "metrics": {}, "issues": [f"undecodable: {str(exc)[:80]}"]}
        scored.append({"index": idx, **result})

    best = max(scored, key=lambda item: item["score"])
    report = {
        "best_index": best["index"],
        "best_score": best["score"],
        "accepted": best["score"] >= SCORE_THRESHOLD,
        "candidate_count": len(candidates),
        "threshold": SCORE_THRESHOLD,
        "candidates": scored,
    }
    return best["index"], report
