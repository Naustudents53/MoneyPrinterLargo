"""Centralized duration presets for YouTube Shorts.

This module avoids cyclic imports by living in its own file and
exposes a single source of truth for the mapping between target
duration (seconds), number of sentences, and number of images.
"""

SHORT_DURATION_PRESETS: dict[int, dict[str, int]] = {
    60: {"sentences": 8, "images": 6},
    120: {"sentences": 16, "images": 9},
    180: {"sentences": 24, "images": 12},
}

ALLOWED_SHORT_DURATIONS = tuple(SHORT_DURATION_PRESETS.keys())
DEFAULT_SHORT_DURATION = 60


def resolve_short_duration(seconds: int | None) -> tuple[int, int, int]:
    """Return (duration_seconds, sentence_count, image_count).

    Falls back to the default preset when *seconds* is missing or invalid.
    """
    if seconds not in SHORT_DURATION_PRESETS:
        seconds = DEFAULT_SHORT_DURATION
    p = SHORT_DURATION_PRESETS[seconds]
    return seconds, p["sentences"], p["images"]
