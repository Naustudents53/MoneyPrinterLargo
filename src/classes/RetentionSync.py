"""RetentionSync: pull REAL audience-retention data from YouTube Studio.

Everything else in the retention stack (RetentionLab, LongRetention) scores
*predictions*. This module closes the loop with ground truth: per-video
"average percentage viewed" and the retention curve that YouTube Studio shows
under Analytics → Engagement, scraped through the same pre-authenticated
Firefox profile the uploader already uses (no API keys, no OAuth).

Layering (so the brittle part stays thin):

  - Pure parsers (`extract_avg_percentage`, `curve_from_svg_path`,
    `biggest_drop`) — fully unit-tested, no Selenium.
  - `fetch_video_retention(browser, video_id)` — the only Selenium-touching
    function; every step guarded, returns {} on any failure.
  - `store_retention(account_id, updates)` — lock + atomic write into the
    same video records the LearningCoach already reads, so reflections can
    learn from "where viewers leave" instead of views alone.

Stored per video: `avg_percentage_viewed` (float, 0-100),
`retention_curve` (list of {position, retention}), `retention_synced_at`.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any

STUDIO_ANALYTICS_URL = (
    "https://studio.youtube.com/video/{video_id}/analytics/tab-interest_viewers/period-default"
)
PAGE_LOAD_WAIT_SECONDS = 12
CURVE_SAMPLES = 21  # one point every 5% of the video

_VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|video/|embed/))([\w-]{11})"
)

# "Average percentage viewed 43.2%" / "Porcentaje promedio reproducido 43,2 %"
_AVG_PCT_RE = re.compile(
    r"(?:average percentage viewed|porcentaje promedio (?:reproducido|visto))"
    r"\D{0,20}?(\d{1,3}(?:[.,]\d{1,2})?)\s*%",
    re.IGNORECASE | re.DOTALL,
)
# Fallback: a bare "43.2%" right next to the metric in either language.
_PCT_NEAR_RE = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%")

_SVG_COORD_RE = re.compile(r"[ML]\s*([\d.+-]+)[\s,]+([\d.+-]+)", re.IGNORECASE)


def extract_video_id(url: str) -> str:
    match = _VIDEO_ID_RE.search(str(url or ""))
    return match.group(1) if match else ""


def extract_avg_percentage(page_text: str) -> float | None:
    """Find 'average percentage viewed' (EN/ES) in Studio page text."""
    text = str(page_text or "")
    match = _AVG_PCT_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    return value if 0.0 <= value <= 100.0 else None


def curve_from_svg_path(d: str) -> list[dict[str, float]]:
    """Convert a Studio retention chart SVG path into a normalized curve.

    Studio draws the retention line as an SVG path of M/L commands in pixel
    space (x grows rightward = video progress, y grows DOWNWARD = lower
    retention). We normalize x to position 0-1 and invert y to retention
    0-100, then resample to CURVE_SAMPLES evenly spaced points so curves from
    different chart sizes are comparable.
    """
    raw = [(float(x), float(y)) for x, y in _SVG_COORD_RE.findall(str(d or ""))]
    if len(raw) < 3:
        return []

    raw.sort(key=lambda p: p[0])
    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_max - x_min <= 0:
        return []
    y_span = (y_max - y_min) or 1.0

    def interp(pos: float) -> float:
        """Linear interpolation of the raw polyline at normalized position."""
        target_x = x_min + pos * (x_max - x_min)
        for i in range(1, len(raw)):
            x0, y0 = raw[i - 1]
            x1, y1 = raw[i]
            if x1 >= target_x:
                if x1 == x0:
                    return y1
                t = (target_x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return raw[-1][1]

    curve = []
    for i in range(CURVE_SAMPLES):
        pos = i / (CURVE_SAMPLES - 1)
        y = interp(pos)
        # SVG y grows downward: top of the chart (y_min) = highest retention.
        retention = (1.0 - (y - y_min) / y_span) * 100.0
        curve.append({"position": round(pos, 3), "retention": round(retention, 1)})
    return curve


def pick_retention_path(path_ds: list[str]) -> str:
    """Choose the SVG path that most plausibly is the retention line.

    Heuristic: the path with the most M/L points wins — axis ticks and area
    fills have few line points or use Z/C-heavy outline commands.
    """
    best_d = ""
    best_points = 0
    for d in path_ds or []:
        points = len(_SVG_COORD_RE.findall(str(d or "")))
        if points > best_points:
            best_points = points
            best_d = str(d)
    return best_d if best_points >= 3 else ""


def biggest_drop(curve: list[dict[str, float]]) -> dict[str, float]:
    """Largest retention drop between consecutive samples (where viewers bail)."""
    worst = {"position": 0.0, "drop": 0.0}
    for i in range(1, len(curve or [])):
        try:
            drop = float(curve[i - 1]["retention"]) - float(curve[i]["retention"])
            if drop > worst["drop"]:
                worst = {"position": float(curve[i]["position"]), "drop": round(drop, 1)}
        except (KeyError, TypeError, ValueError):
            continue
    return worst


def fetch_video_retention(browser, video_id: str) -> dict[str, Any]:
    """Scrape one video's retention from Studio. Returns {} on any failure."""
    import time

    if not video_id:
        return {}
    try:
        browser.get(STUDIO_ANALYTICS_URL.format(video_id=video_id))
        time.sleep(PAGE_LOAD_WAIT_SECONDS)

        page_text = ""
        try:
            page_text = browser.execute_script(
                "return document.body ? document.body.innerText : '';"
            ) or ""
        except Exception:
            pass
        avg_pct = extract_avg_percentage(page_text)

        curve: list[dict[str, float]] = []
        try:
            path_ds = browser.execute_script(
                "return Array.from(document.querySelectorAll("
                "'yta-line-chart svg path, ytcp-line-chart svg path, svg path'"
                ")).map(p => p.getAttribute('d') || '').filter(d => d.length > 30);"
            ) or []
            best = pick_retention_path([str(d) for d in path_ds])
            if best:
                curve = curve_from_svg_path(best)
        except Exception:
            curve = []

        if avg_pct is None and not curve:
            return {}

        result: dict[str, Any] = {
            "retention_synced_at": datetime.datetime.now(datetime.timezone.utc)
            .isoformat(),
        }
        if avg_pct is not None:
            result["avg_percentage_viewed"] = avg_pct
        if curve:
            result["retention_curve"] = curve
            result["retention_biggest_drop"] = biggest_drop(curve)
        return result
    except Exception:
        return {}


def store_retention(account_id: str, updates: dict[str, dict[str, Any]]) -> int:
    """Merge per-video retention data into youtube.json. Returns videos updated.

    `updates` maps video_id -> retention fields. Read-modify-write under the
    shared cache lock with an atomic replace, same as every other writer.
    """
    if not updates:
        return 0
    from cache import get_youtube_cache_path, json_write_lock, atomic_write_json

    cache_path = get_youtube_cache_path()
    if not os.path.exists(cache_path):
        return 0

    written = 0
    with json_write_lock(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {"accounts": []}
        for account in data.get("accounts", []):
            if account.get("id") != account_id:
                continue
            for video in account.get("videos", []) or []:
                vid = extract_video_id(video.get("url", "") or "")
                if vid and vid in updates:
                    video.update(updates[vid])
                    written += 1
        if written:
            atomic_write_json(cache_path, data)
    return written


def sync_account_retention(
    browser,
    account_id: str,
    videos: list[dict[str, Any]],
    max_videos: int = 10,
) -> dict[str, Any]:
    """Fetch + store retention for an account's most recent videos.

    Returns {"fetched": n, "stored": n, "failed": n}. Never raises.
    """
    recent = sorted(
        (v for v in (videos or []) if extract_video_id(v.get("url", "") or "")),
        key=lambda v: v.get("date", ""),
        reverse=True,
    )[: max(1, max_videos)]

    updates: dict[str, dict[str, Any]] = {}
    failed = 0
    for video in recent:
        vid = extract_video_id(video.get("url", ""))
        result = fetch_video_retention(browser, vid)
        if result:
            updates[vid] = result
        else:
            failed += 1

    stored = 0
    try:
        stored = store_retention(account_id, updates)
    except Exception:
        pass
    return {"fetched": len(updates), "stored": stored, "failed": failed}
