"""Winner Remix: deliberately revisit a channel's best video in disguise.

The normal topic pipeline (`YouTube.generate_topic`) refuses to repeat any past
subject. This module does the opposite on a controlled cadence: roughly 1 in
every `ratio` videos, it picks one of the channel's best performers and asks the
LLM for a *different concrete subject within the same subtheme*, so the new video
rides what already works without reading as the same video.

Memory & learning live on the video records themselves (`.mp/youtube.json`):
every remix video is tagged with `is_remix`, `remix_source_url` and
`remix_subtheme`. Because view counts are synced back onto those same records,
the feedback loop is free:

  - "no repetir el mismo video": a winner whose url was already used as a remix
    source is never picked again.
  - learning: subthemes whose past remix became a winner are boosted; subthemes
    whose past remix flopped are suppressed when weighting candidates.

Stdlib + `topic_dedupe` only (no heavy imports), so it stays cheap to import.
"""

from __future__ import annotations

import random
import unicodedata
from typing import Any

from topic_dedupe import distinctive_anchors, find_duplicate

WINNER_VIEWS = 1000
WEAK_VIEWS = 100

# Weighting multipliers applied when a candidate winner shares a subtheme with a
# past remix outcome. A flopped subtheme is pushed down hard; a proven one up.
_WEAK_SUBTHEME_PENALTY = 0.2
_WINNING_SUBTHEME_BOOST = 2.0


def video_views(video: dict[str, Any]) -> int | None:
    """Parse a video's view count, returning None when missing or invalid."""
    try:
        number = int(video.get("view_count"))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def is_remix(video: dict[str, Any]) -> bool:
    return bool(video.get("is_remix"))


def _is_short(video: dict[str, Any]) -> bool:
    if "is_short" in video:
        return bool(video.get("is_short"))
    text = (
        f"{video.get('title') or ''} {video.get('description') or ''} "
        f"{video.get('url') or ''}"
    ).lower()
    return "#short" in text or "/shorts/" in text


def remixed_source_urls(videos: list[dict[str, Any]]) -> set[str]:
    """URLs of winners already consumed as a remix source (never reuse them)."""
    used: set[str] = set()
    for video in videos or []:
        url = str(video.get("remix_source_url") or "").strip()
        if url:
            used.add(url)
    return used


def should_remix(ratio: int, rng: random.Random | None = None) -> bool:
    """Probabilistic gate: roughly 1 in `ratio` rolls returns True."""
    try:
        ratio_int = int(ratio)
    except (TypeError, ValueError):
        return False
    if ratio_int <= 0:
        return False
    roll = (rng or random).random()
    return roll < (1.0 / ratio_int)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _subtheme_matches(candidate_text: str, subtheme: str) -> bool:
    """True when the candidate clearly belongs to the same subtheme.

    Uses the subtheme's distinctive anchors (named subjects) and falls back to
    a normalized substring test, so generic phrases still match.
    """
    if not subtheme:
        return False
    cand_anchors = distinctive_anchors(candidate_text)
    sub_anchors = distinctive_anchors(subtheme)
    if cand_anchors and sub_anchors and (cand_anchors & sub_anchors):
        return True
    return _normalize(subtheme) in _normalize(candidate_text)


def evaluate_history(videos: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Classify past remix outcomes into winning vs weak subthemes."""
    winning: set[str] = set()
    weak: set[str] = set()
    for video in videos or []:
        if not is_remix(video):
            continue
        views = video_views(video)
        if views is None:
            continue
        # Only the recorded source subtheme counts: falling back to the remix's
        # own subject would bias unrelated winners via substring matching.
        subtheme = str(video.get("remix_subtheme") or "").strip()
        if not subtheme:
            continue
        if views >= WINNER_VIEWS:
            winning.add(subtheme)
        elif views < WEAK_VIEWS:
            weak.add(subtheme)
    return {"winning_subthemes": winning, "weak_subthemes": weak}


def pick_winner(
    videos: list[dict[str, Any]],
    min_views: int = WINNER_VIEWS,
    top_n: int = 5,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Pick a winning video to remix from, weighted and learning-aware.

    Filters: must be a Short with views >= min_views, and must not already have
    been used as a remix source. Weighting: base views, scaled up for proven
    subthemes and down for subthemes whose past remix flopped. A weighted random
    choice over the top N keeps variety instead of always the single best.
    """
    rng = rng or random
    used = remixed_source_urls(videos)
    learning = evaluate_history(videos)
    winning_subthemes = learning["winning_subthemes"]
    weak_subthemes = learning["weak_subthemes"]

    scored: list[tuple[dict[str, Any], float]] = []
    for video in videos or []:
        if is_remix(video) or not _is_short(video):
            continue
        views = video_views(video)
        if views is None or views < min_views:
            continue
        url = str(video.get("url") or "").strip()
        if url and url in used:
            continue

        weight = float(views)
        subject = str(video.get("subject") or video.get("title") or "")
        # A proven flop wins over a proven win: never multiply both together.
        if any(_subtheme_matches(subject, sub) for sub in weak_subthemes):
            weight *= _WEAK_SUBTHEME_PENALTY
        elif any(_subtheme_matches(subject, sub) for sub in winning_subthemes):
            weight *= _WINNING_SUBTHEME_BOOST
        scored.append((video, max(weight, 1.0)))

    if not scored:
        return None

    scored.sort(key=lambda pair: pair[1], reverse=True)
    top = scored[:max(1, top_n)]
    population = [video for video, _ in top]
    weights = [weight for _, weight in top]
    return rng.choices(population, weights=weights, k=1)[0]


def is_acceptable_remix(
    candidate: str,
    winner: dict[str, Any],
    past_topics: list[str],
) -> bool:
    """Validate a generated remix topic.

    Rejects: empty topics, anything that duplicates a published video, and
    topics that reuse the winner's exact distinctive subject (which would read
    as the same video instead of a disguised sibling).
    """
    candidate = (candidate or "").strip()
    if not candidate:
        return False
    if find_duplicate(candidate, past_topics or []):
        return False
    winner_text = f"{winner.get('subject') or ''} {winner.get('title') or ''}"
    winner_anchors = distinctive_anchors(winner_text)
    candidate_anchors = distinctive_anchors(candidate)
    if winner_anchors and (winner_anchors & candidate_anchors):
        return False
    return True


def build_remix_prompt(
    winner: dict[str, Any],
    niche: str,
    language: str,
    directive: str = "",
) -> str:
    """Prompt asking for a fresh subject within the winner's subtheme.

    `directive` (the learned playbook) is inserted BEFORE the strict output
    format rules so those rules remain the last thing the model reads —
    appending after them measurably degrades format compliance.
    """
    source = str(winner.get("subject") or winner.get("title") or "").strip()
    directive_block = f"\n{directive.strip()}\n" if directive and directive.strip() else ""
    return f"""Your channel's best-performing video was about this subject:

BEST VIDEO SUBJECT: {source}

YOUR NICHE (stay strictly within it): {niche}

Generate ONE new, specific topic that belongs to the SAME broad subtheme as the
best video, but is about a DIFFERENT concrete subject (a different named object,
person, event, place, or phenomenon). It must NOT mention or be recognizable as
the same specific subject as the best video — a viewer should not realize it is a
follow-up on the same thing. It should simply feel like another strong video in
the same vein.

RULES:
- Same subtheme, DIFFERENT specific subject. Do not name the best video's subject.
- One concrete real subject, not a broad category and not fiction.
- Must clearly belong to the niche "{niche}".
{directive_block}
OUTPUT FORMAT (strict):
- Return ONLY the topic as one plain sentence.
- NO markdown, NO prefixes like "Topic:" or "Tema:", NO surrounding quotes.
- WRITE ENTIRELY IN {language}. Every word must be in {language}."""
