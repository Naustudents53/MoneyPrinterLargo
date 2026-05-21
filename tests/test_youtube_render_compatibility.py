import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.YouTube import YouTube


def test_mp4_render_params_force_player_compatible_pixel_format():
    params = YouTube._mp4_compat_ffmpeg_params()

    assert params[params.index("-pix_fmt") + 1] == "yuv420p"
    assert params[params.index("-movflags") + 1] == "+faststart"


def test_ass_timestamp_uses_centiseconds():
    assert YouTube._ass_timestamp(65.347) == "0:01:05.35"
    assert YouTube._ass_timestamp(-1) == "0:00:00.00"


def test_ffmpeg_filter_path_escapes_windows_drive():
    escaped = YouTube._ffmpeg_filter_escape_path(r"C:\Users\Daniel\subs file.ass")

    assert escaped.startswith(r"C\:/")
    assert "\\" not in escaped.replace(r"\:", "")


def test_karaoke_ass_writer_preserves_word_highlight(tmp_path):
    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = [
        {"start": 0.0, "end": 0.4, "word": "hola"},
        {"start": 0.4, "end": 0.8, "word": "mundo"},
    ]
    youtube.script = "hola mundo"
    youtube.subject = "test"
    youtube._retention_mode = "standard"

    ass_path = tmp_path / "karaoke.ass"
    assert youtube._write_karaoke_ass_subtitles(str(ass_path), 1.0) is True

    text = ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in text
    assert r"{\an8\pos(540,1300)}" in text
    assert r"{\c&H0000D7FF&}HOLA" in text
    assert r"{\c&H0000D7FF&}MUNDO" in text


def test_long_clip_durations_account_for_crossfades_and_tail():
    durations = YouTube._long_clip_durations(
        num_clips=4,
        max_duration=100.0,
        crossfade=0.8,
        extra_tail=1.5,
    )

    visible_duration = sum(durations) - (0.8 * 3)

    assert len(durations) == 4
    assert visible_duration == pytest.approx(101.5)


def test_landscape_karaoke_ass_writer_uses_16_9_canvas(tmp_path):
    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = [
        {"start": 0.0, "end": 0.4, "word": "hola"},
        {"start": 0.4, "end": 0.8, "word": "mundo"},
    ]
    youtube.script = "hola mundo"
    youtube.subject = "test"

    ass_path = tmp_path / "long_karaoke.ass"
    assert youtube._write_karaoke_ass_subtitles_landscape(str(ass_path), 2.0) is True

    text = ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 1920" in text
    assert "PlayResY: 1080" in text
    assert r"{\an8\pos(960,820)}" in text
    assert r"{\c&H0000D7FF&}HOLA" in text
