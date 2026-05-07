"""Centralized duration presets for YouTube Shorts.

Single source of truth for the mapping target_duration_seconds → sentence
count, target word count, and image count.

Calibration notes
-----------------
A naive preset like "8 sentences for 60s, 16 for 120s, 24 for 180s" looks
right on paper but undershoots in practice: KittenTTS / Edge-TTS produce
short Spanish sentences in roughly 4-5 seconds, not the 7.5s the naive
math assumes. That caused the user-reported bug where picking 2 min
yielded ~1 min videos and picking 3 min yielded ~2 min.

Empirically, narrated Spanish at the default rate runs ~150 words per
minute (≈ 2.5 wps). The presets below target that wpm with a small
safety buffer so the encoded video lands ON or slightly ABOVE the
selected duration, never under.

  60s  →  ~150 words → 12 sentences (~12-14 words each)
  120s →  ~310 words → 22 sentences (~14 words each)
  180s →  ~470 words → 32 sentences (~14-15 words each)

`words` is the target word count we tell the LLM to aim for. It's the
load-bearing number — the script-generation prompt enforces words first
and sentences second, because LLMs honor word counts more reliably than
sentence counts.
"""

from __future__ import annotations


SHORT_DURATION_PRESETS: dict[int, dict[str, int]] = {
    60:  {"sentences": 12, "words": 150, "images": 6},
    120: {"sentences": 22, "words": 310, "images": 10},
    180: {"sentences": 32, "words": 470, "images": 14},
}

ALLOWED_SHORT_DURATIONS: tuple[int, ...] = tuple(SHORT_DURATION_PRESETS.keys())
DEFAULT_SHORT_DURATION: int = 60


def resolve_short_duration(
    seconds: int | None,
) -> tuple[int, int, int, int]:
    """Return ``(duration_seconds, sentence_count, word_count, image_count)``.

    Falls back to the default preset (60s) when *seconds* is missing or
    not in :data:`SHORT_DURATION_PRESETS`.
    """
    if seconds not in SHORT_DURATION_PRESETS:
        seconds = DEFAULT_SHORT_DURATION
    p = SHORT_DURATION_PRESETS[seconds]
    return seconds, p["sentences"], p["words"], p["images"]
