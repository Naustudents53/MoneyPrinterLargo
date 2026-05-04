"""
Config getters for the YouTube upload pipeline. Defaults preserve the
exact behavior of the legacy hardcoded constants.

Override in `config.json` under the `youtube_upload` key, e.g.:

    "youtube_upload": {
      "thumbnail":     {"max_attempts": 3, "verify_timeout_s": 180, "retry_backoff_s": 30},
      "short_polling": {"max_wait_s": 1800, "poll_s": 8,  "refresh_s": 60},
      "long_polling":  {"max_wait_s": 10800,"poll_s": 15, "refresh_s": 120}
    }
"""

from __future__ import annotations

from config import _load_config


_DEFAULTS = {
    "thumbnail": {
        "max_attempts": 3,
        "verify_timeout_s": 180,
        "retry_backoff_s": 30,
        "verify_poll_s": 2,
        "max_bytes": 2 * 1024 * 1024,  # YouTube's hard cap
    },
    "short_polling": {
        "max_wait_s": 1800,    # 30 min
        "poll_s": 8,
        "refresh_s": 60,
        "max_studio_error_retries": 5,
    },
    "long_polling": {
        "max_wait_s": 10800,   # 3 h
        "poll_s": 15,
        "refresh_s": 120,
        "max_studio_error_retries": 5,
    },
    "title_max_chars": 100,
    "description_max_chars": 5000,
    "stale_uploading_hours": 6,
    "page_load_timeout_s": 90,
    "script_timeout_s": 60,
    "default_wait_s": 30,
}


def _section(name: str) -> dict:
    cfg = _load_config().get("youtube_upload", {}) or {}
    user = cfg.get(name, {}) or {}
    base = dict(_DEFAULTS.get(name, {}) if isinstance(_DEFAULTS.get(name), dict) else {})
    base.update(user)
    return base


def thumbnail_settings() -> dict:
    return _section("thumbnail")


def short_polling_settings() -> dict:
    return _section("short_polling")


def long_polling_settings() -> dict:
    return _section("long_polling")


def title_max_chars() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "title_max_chars", _DEFAULTS["title_max_chars"]))


def description_max_chars() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "description_max_chars", _DEFAULTS["description_max_chars"]))


def stale_uploading_hours() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "stale_uploading_hours", _DEFAULTS["stale_uploading_hours"]))


def page_load_timeout_s() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "page_load_timeout_s", _DEFAULTS["page_load_timeout_s"]))


def script_timeout_s() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "script_timeout_s", _DEFAULTS["script_timeout_s"]))


def default_wait_s() -> int:
    return int(_load_config().get("youtube_upload", {}).get(
        "default_wait_s", _DEFAULTS["default_wait_s"]))
