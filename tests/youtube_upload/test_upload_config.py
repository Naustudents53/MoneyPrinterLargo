"""
Tests for `youtube_upload.upload_config`. Verify defaults and that
user-provided overrides in config.json take precedence.
"""

from unittest.mock import patch

from youtube_upload import upload_config


def test_defaults_when_no_user_config():
    with patch("youtube_upload.upload_config._load_config", return_value={}):
        thumb = upload_config.thumbnail_settings()
        assert thumb["max_attempts"] == 3
        assert thumb["verify_timeout_s"] == 180

        short = upload_config.short_polling_settings()
        assert short["max_wait_s"] == 1800

        long = upload_config.long_polling_settings()
        assert long["max_wait_s"] == 10800

        assert upload_config.title_max_chars() == 100
        assert upload_config.description_max_chars() == 5000
        assert upload_config.stale_uploading_hours() == 6


def test_user_overrides_merge_with_defaults():
    cfg = {
        "youtube_upload": {
            "thumbnail": {"max_attempts": 5},  # only override one key
            "title_max_chars": 70,
        }
    }
    with patch("youtube_upload.upload_config._load_config", return_value=cfg):
        thumb = upload_config.thumbnail_settings()
        # Override applied
        assert thumb["max_attempts"] == 5
        # Other defaults still present
        assert thumb["verify_timeout_s"] == 180
        assert thumb["retry_backoff_s"] == 30

        assert upload_config.title_max_chars() == 70
        # Non-overridden key keeps default
        assert upload_config.description_max_chars() == 5000
