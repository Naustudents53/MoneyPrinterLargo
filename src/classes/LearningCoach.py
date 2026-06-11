"""LearningCoach: an LLM-style coach that reflects on a channel's results.

Whenever YouTube stats are synced, the channel's video records gain fresh
view/like/comment numbers. This module turns that signal into *natural-language
lessons* by asking Claude (`claude -p`, via an injected `ask` callable) what the
channel should keep doing and stop doing. The lessons + a small "playbook" are
persisted per account and injected back into topic, remix, hook and script
generation so the LLM steadily improves.

Design constraints:

  - Reflect at most once per *new data*. A signature over (url, view_count,
    stats_synced_at) gates it: unchanged signature → the coach already reflected
    on this data → skip. Changed → reflect once and store the new signature.
  - Stdlib only; the LLM call is injected so the core stays pure and testable.
  - Never break the sync: `reflect_after_sync` swallows every error.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from typing import Any, Callable

_PLAYBOOK_KEYS = ("topic_guidance", "hook_guidance", "script_guidance", "avoid")
_DEFAULT_MAX_LESSONS = 30


def _video_views(video: dict[str, Any]) -> int | None:
    try:
        number = int(video.get("view_count"))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def data_signature(videos: list[dict[str, Any]]) -> str:
    """Stable hash of the scored videos' (url, views).

    Deliberately excludes `stats_synced_at`: it changes on every sync even
    when the numbers do not, which would defeat the "skip unchanged data"
    gate and trigger an LLM call per sync.

    Returns "" when there is nothing with views to learn from, so callers can
    cheaply treat "no data" as "nothing to reflect on".
    """
    items: list[tuple[str, int]] = []
    for video in videos or []:
        views = _video_views(video)
        if views is None:
            continue
        url = str(video.get("url") or "")
        items.append((url, views))
    if not items:
        return ""
    items.sort()
    payload = json.dumps(items, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_reflection_due(learning: dict[str, Any] | None, videos: list[dict[str, Any]]) -> bool:
    """True only when there is new, unreflected data to learn from."""
    signature = data_signature(videos)
    if not signature:
        return False
    previous = str((learning or {}).get("last_data_signature") or "")
    return signature != previous


def parse_reflection(text: str) -> dict[str, Any]:
    """Best-effort extract of the JSON object from an LLM answer.

    Tolerates ```json fences and surrounding prose by grabbing the first
    balanced-looking `{ ... }` span. Returns {} when nothing parses.
    """
    if not text:
        return {}
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def merge_lessons(
    existing: list[str] | None,
    new: list[str] | None,
    max_lessons: int = _DEFAULT_MAX_LESSONS,
) -> list[str]:
    """Append new lessons, drop case-insensitive duplicates, keep the newest."""
    merged: list[str] = []
    seen: set[str] = set()
    for lesson in list(existing or []) + list(new or []):
        text = str(lesson or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            # Re-seen: move it to the end (most recent wins) by dropping the old.
            merged = [item for item in merged if item.lower() != key]
        seen.add(key)
        merged.append(text)
    if max_lessons > 0 and len(merged) > max_lessons:
        merged = merged[-max_lessons:]
    return merged


def build_reflection_prompt(
    account: dict[str, Any],
    videos: list[dict[str, Any]],
    learning: dict[str, Any] | None,
) -> str:
    """Ask the coach to refine prior lessons given the latest performance."""
    nickname = str((account or {}).get("nickname") or (account or {}).get("name") or "this channel")
    niche = str((account or {}).get("niche") or (account or {}).get("topic") or "").strip()

    scored = [v for v in (videos or []) if _video_views(v) is not None]
    scored.sort(key=lambda v: _video_views(v) or 0, reverse=True)
    top = scored[:10]
    bottom = scored[-10:] if len(scored) > 10 else []

    def _line(video: dict[str, Any]) -> str:
        return f"- {_video_views(video)} views :: {str(video.get('subject') or video.get('title') or '').strip()}"

    best_block = "\n".join(_line(v) for v in top) or "(no data yet)"
    worst_block = "\n".join(_line(v) for v in bottom) or "(not enough data)"

    prior_lessons = (learning or {}).get("lessons") or []
    prior_block = "\n".join(f"- {l}" for l in prior_lessons[-15:]) or "(none yet)"

    return f"""You are the performance coach for a YouTube channel called "{nickname}".
Niche: {niche or "(unspecified)"}.

You are shown the channel's best and worst performers by view count. Your job is
to REFINE the existing lessons — do not just repeat them. Add what is newly
supported by the data, sharpen what is vague, and drop nothing important.

BEST PERFORMERS:
{best_block}

WORST PERFORMERS:
{worst_block}

EXISTING LESSONS (refine, don't restate verbatim):
{prior_block}

Return ONLY a strict JSON object, no prose, no markdown fences, with this shape:
{{
  "lessons": ["short, concrete, actionable lessons (max ~8)"],
  "playbook": {{
    "topic_guidance": "what kinds of topics to choose",
    "hook_guidance": "how the first line / hook should work",
    "script_guidance": "how the script body should be written",
    "avoid": "patterns that correlate with weak performance"
  }}
}}
Every value must be a plain string. Write in the same language as the topics above."""


def run_reflection(
    account: dict[str, Any],
    videos: list[dict[str, Any]],
    learning: dict[str, Any] | None,
    ask: Callable[[str], str],
    *,
    max_lessons: int = _DEFAULT_MAX_LESSONS,
) -> dict[str, Any]:
    """Run one reflection pass and return the updated learning dict.

    On `ask` failure — raised exception, empty answer, or an unparseable
    answer — the learning is returned unchanged and the signature is NOT
    advanced, so the next sync retries instead of silently consuming the
    data without having learned anything from it.
    """
    updated = dict(learning or {})
    prompt = build_reflection_prompt(account, videos, updated)
    try:
        raw = ask(prompt)
    except Exception:
        return updated

    parsed = parse_reflection(raw or "")
    if not parsed:
        return updated

    new_lessons = parsed.get("lessons")
    updated["lessons"] = merge_lessons(
        updated.get("lessons"),
        new_lessons if isinstance(new_lessons, list) else [],
        max_lessons,
    )
    playbook = parsed.get("playbook")
    if isinstance(playbook, dict):
        merged_pb = dict(updated.get("playbook") or {})
        for key in _PLAYBOOK_KEYS:
            value = str(playbook.get(key) or "").strip()
            if value:
                merged_pb[key] = value
        updated["playbook"] = merged_pb

    updated["last_data_signature"] = data_signature(videos)
    updated["last_reflection_at"] = _now_iso()
    updated["videos_seen"] = sum(1 for v in (videos or []) if _video_views(v) is not None)
    return updated


def injected_directive(learning: dict[str, Any] | None) -> str:
    """Render the learned playbook + lessons as a directive for generation.

    Returns "" when there is nothing learned yet, so callers can append it
    unconditionally without polluting prompts.
    """
    learning = learning or {}
    playbook = learning.get("playbook") or {}
    lessons = learning.get("lessons") or []

    sections: list[str] = []
    labels = {
        "topic_guidance": "Topics",
        "hook_guidance": "Hook",
        "script_guidance": "Script",
        "avoid": "Avoid",
    }
    for key in _PLAYBOOK_KEYS:
        value = str(playbook.get(key) or "").strip()
        if value:
            sections.append(f"{labels[key]}: {value}")

    for lesson in lessons[-8:]:
        text = str(lesson or "").strip()
        if text:
            sections.append(f"- {text}")

    if not sections:
        return ""
    body = "\n".join(sections)
    return (
        "LEARNED PLAYBOOK (apply what has worked for this channel; "
        "do not mention this block in the output):\n" + body
    )


def directive_for_account(account_id: str) -> str:
    """Load an account's learning and render its directive. Safe on any error."""
    try:
        import cache  # type: ignore

        return injected_directive(cache.get_learning(account_id))
    except Exception:
        return ""


def reflect_after_sync(account: dict[str, Any]) -> bool:
    """Reflect once on freshly-synced data for one account.

    Fully guarded: any failure (disabled, no new data, LLM/CLI error) returns
    False and never raises, so a sync run is never broken by the coach.
    Returns True only when a new reflection was produced and persisted.
    """
    try:
        import config  # type: ignore
        import cache  # type: ignore
        from llm_provider import _generate_text_claude_cli  # type: ignore

        if not config.get_learning_enabled():
            return False

        account_id = str((account or {}).get("id") or "")
        if not account_id:
            return False

        videos = (account or {}).get("videos") or []
        learning = cache.get_learning(account_id)
        if not is_reflection_due(learning, videos):
            return False

        model = config.get_learning_model()
        max_lessons = config.get_learning_max_lessons()

        def ask(prompt: str) -> str:
            return _generate_text_claude_cli(prompt, model=model or None)

        updated = run_reflection(account, videos, learning, ask, max_lessons=max_lessons)
        if updated.get("last_data_signature") == learning.get("last_data_signature"):
            return False  # ask failed; signature not advanced — retry next sync

        cache.save_learning(account_id, updated)
        return True
    except Exception:
        return False
