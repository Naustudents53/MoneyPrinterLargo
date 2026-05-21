import sys
from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from classes.YouTube import YouTube


def test_mp4_render_params_force_player_compatible_pixel_format():
    params = YouTube._mp4_compat_ffmpeg_params()

    assert params[params.index("-pix_fmt") + 1] == "yuv420p"
    assert params[params.index("-movflags") + 1] == "+faststart"


def test_image_normalization_crops_to_target_aspect_without_distortion():
    source = Image.new("RGB", (800, 600), "red")
    out = BytesIO()
    source.save(out, format="PNG")

    normalized = YouTube._normalize_image_bytes_to_size(out.getvalue(), 216, 384)

    with Image.open(BytesIO(normalized)) as img:
        assert img.size == (216, 384)


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


def test_karaoke_grouping_breaks_on_sentence_pause(tmp_path):
    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = [
        {"start": 0.0, "end": 0.2, "word": "esto"},
        {"start": 0.22, "end": 0.45, "word": "arde."},
        {"start": 0.9, "end": 1.1, "word": "mira"},
        {"start": 1.12, "end": 1.35, "word": "ahora"},
    ]
    youtube.script = "esto arde. mira ahora"
    youtube.subject = "test"
    youtube._retention_mode = "standard"

    ass_path = tmp_path / "karaoke_grouped.ass"
    assert youtube._write_karaoke_ass_subtitles(str(ass_path), 2.0) is True

    dialogues = [
        line for line in ass_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Dialogue:")
    ]
    assert "MIRA" not in dialogues[0]
    assert "ESTO" not in dialogues[2]


def test_karaoke_ass_writer_uses_configurable_subtitle_style(tmp_path, monkeypatch):
    import classes.YouTube as youtube_module

    monkeypatch.setattr(youtube_module, "get_subtitle_font_size", lambda default: 72, raising=False)
    monkeypatch.setattr(youtube_module, "get_subtitle_position_y", lambda default: 1200, raising=False)
    monkeypatch.setattr(youtube_module, "get_subtitle_max_words_per_group", lambda default: 2, raising=False)

    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = [
        {"start": 0.0, "end": 0.3, "word": "hola"},
        {"start": 0.3, "end": 0.6, "word": "mundo"},
        {"start": 0.6, "end": 0.9, "word": "brillante"},
    ]
    youtube.script = "hola mundo brillante"
    youtube.subject = "test"
    youtube._retention_mode = "standard"

    ass_path = tmp_path / "styled_karaoke.ass"
    assert youtube._write_karaoke_ass_subtitles(str(ass_path), 1.2) is True

    text = ass_path.read_text(encoding="utf-8")
    assert "Style: Karaoke,Poppins Black,72," in text
    assert r"{\an8\pos(540,1200)}" in text


def test_ensure_karaoke_timestamps_tries_whisper_before_estimate(monkeypatch):
    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = None
    youtube.script = "hola mundo"
    expected = [{"start": 0.0, "end": 0.4, "word": "hola"}]

    monkeypatch.setattr(
        youtube,
        "_generate_word_timestamps_local_whisper",
        lambda audio_path: expected,
        raising=False,
    )
    monkeypatch.setattr(
        youtube,
        "_estimate_word_timestamps",
        lambda _duration: pytest.fail("estimated timestamps should only be the last fallback"),
    )

    assert youtube._ensure_karaoke_word_timestamps("audio.wav", 1.0) == expected
    assert youtube.word_timestamps == expected


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


def test_ffmpeg_filters_use_configured_4k_canvas():
    youtube = YouTube.__new__(YouTube)

    short_filter = youtube._short_ffmpeg_filter_complex(
        image_count=1,
        durations=[1.0],
        fps=60,
        output_size=(2160, 3840),
        crossfade=0,
        ken_burns_enabled=False,
        karaoke_ass_path="",
        music_volume=0.1,
        audio_duration=1.0,
    )
    assert "scale=2160:3840" in short_filter
    assert "crop=2160:3840" in short_filter

    long_filter = youtube._long_ffmpeg_filter_complex(
        image_count=1,
        durations=[1.0],
        fps=60,
        output_size=(3840, 2160),
        crossfade=0,
        karaoke_ass_path="",
        music_volume=0.1,
        audio_duration=1.0,
        total_duration=1.0,
        extra_tail=0,
    )
    assert "scale=3840:2160" in long_filter
    assert "crop=3840:2160" in long_filter


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


def test_karaoke_ass_writers_accept_4k_canvases(tmp_path):
    youtube = YouTube.__new__(YouTube)
    youtube.word_timestamps = [
        {"start": 0.0, "end": 0.4, "word": "hola"},
        {"start": 0.4, "end": 0.8, "word": "mundo"},
    ]
    youtube.script = "hola mundo"
    youtube.subject = "test"
    youtube._retention_mode = "standard"

    short_ass_path = tmp_path / "short_4k.ass"
    assert youtube._write_karaoke_ass_subtitles(
        str(short_ass_path),
        1.0,
        (2160, 3840),
    ) is True

    short_text = short_ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 2160" in short_text
    assert "PlayResY: 3840" in short_text
    assert r"{\an8\pos(1080,2600)}" in short_text

    long_ass_path = tmp_path / "long_4k.ass"
    assert youtube._write_karaoke_ass_subtitles_landscape(
        str(long_ass_path),
        2.0,
        (3840, 2160),
    ) is True

    long_text = long_ass_path.read_text(encoding="utf-8")
    assert "PlayResX: 3840" in long_text
    assert "PlayResY: 2160" in long_text
    assert r"{\an8\pos(1920,1640)}" in long_text
