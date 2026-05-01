import os
import sys
import json
import srt_equalizer

_CONFIG_CACHE = None
_CONFIG_MTIME = None


def _load_config() -> dict:
    global _CONFIG_CACHE, _CONFIG_MTIME
    config_path = os.path.join(ROOT_DIR, "config.json")
    try:
        mtime = os.path.getmtime(config_path)
    except OSError:
        return {}
    if _CONFIG_CACHE is not None and _CONFIG_MTIME == mtime:
        return _CONFIG_CACHE
    with open(config_path, "r", encoding="utf-8") as file:
        _CONFIG_CACHE = json.load(file)
    _CONFIG_MTIME = mtime
    return _CONFIG_CACHE


from termcolor import colored

ROOT_DIR = os.path.dirname(sys.path[0])


def assert_folder_structure() -> None:
    mp_path = os.path.join(ROOT_DIR, ".mp")
    if not os.path.exists(mp_path):
        if _load_config().get("verbose", True):
            print(colored(f"=> Creating .mp folder at {mp_path}", "green"))
        os.makedirs(mp_path)


def get_first_time_running() -> bool:
    return not os.path.exists(os.path.join(ROOT_DIR, ".mp"))


def get_email_credentials() -> dict:
    return _load_config().get("email", {})


def get_verbose() -> bool:
    return _load_config().get("verbose", True)


def get_firefox_profile_path() -> str:
    return _load_config().get("firefox_profile", "")


def get_headless() -> bool:
    return _load_config().get("headless", False)


def get_ollama_base_url() -> str:
    return _load_config().get("ollama_base_url", "http://127.0.0.1:11434")


def get_ollama_model() -> str:
    return _load_config().get("ollama_model", "")


def get_long_video_llm_model() -> str:
    return _load_config().get("long_video_llm_model", "deepseek-v4-pro:cloud")


def get_twitter_language() -> str:
    return _load_config().get("twitter_language", "English")


def get_nanobanana2_api_base_url() -> str:
    return _load_config().get(
        "nanobanana2_api_base_url",
        "https://generativelanguage.googleapis.com/v1beta",
    )


def get_nanobanana2_api_key() -> str:
    configured = _load_config().get("nanobanana2_api_key", "")
    return configured or os.environ.get("GEMINI_API_KEY", "")


def get_nanobanana2_model() -> str:
    return _load_config().get("nanobanana2_model", "gemini-3.1-flash-image-preview")


def get_nanobanana2_aspect_ratio() -> str:
    return _load_config().get("nanobanana2_aspect_ratio", "9:16")


def get_threads() -> int:
    return _load_config().get("threads", 2)


def get_zip_url() -> str:
    return _load_config().get("zip_url", "")


def get_is_for_kids() -> bool:
    return _load_config().get("is_for_kids", False)


def get_google_maps_scraper_zip_url() -> str:
    return _load_config().get("google_maps_scraper", "")


def get_google_maps_scraper_niche() -> str:
    return _load_config().get("google_maps_scraper_niche", "")


def get_scraper_timeout() -> int:
    return _load_config().get("scraper_timeout", 300)


def get_outreach_message_subject() -> str:
    return _load_config().get("outreach_message_subject", "")


def get_outreach_message_body_file() -> str:
    return _load_config().get("outreach_message_body_file", "")


def get_tts_voice() -> str:
    return _load_config().get("tts_voice", "Jasper")


def get_assemblyai_api_key() -> str:
    return _load_config().get("assembly_ai_api_key", "")


def get_pexels_api_key() -> str:
    configured = _load_config().get("pexels_api_key", "")
    return configured or os.environ.get("PEXELS_API_KEY", "")


def get_pixabay_api_key() -> str:
    configured = _load_config().get("pixabay_api_key", "")
    return configured or os.environ.get("PIXABAY_API_KEY", "")


def get_ideogram_api_key() -> str:
    configured = _load_config().get("ideogram_api_key", "")
    return configured or os.environ.get("IDEOGRAM_API_KEY", "")


def get_leonardo_api_key() -> str:
    configured = _load_config().get("leonardo_api_key", "")
    return configured or os.environ.get("LEONARDO_API_KEY", "")


def get_hf_api_key() -> str:
    configured = _load_config().get("hf_api_key", "")
    return configured or os.environ.get("HF_TOKEN", "")


def get_stt_provider() -> str:
    return _load_config().get("stt_provider", "local_whisper")


def get_whisper_model() -> str:
    return _load_config().get("whisper_model", "base")


def get_whisper_device() -> str:
    return _load_config().get("whisper_device", "auto")


def get_whisper_compute_type() -> str:
    return _load_config().get("whisper_compute_type", "int8")


def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
    srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)


def get_font() -> str:
    return _load_config().get("font", "bold_font.ttf")


def get_fonts_dir() -> str:
    return os.path.join(ROOT_DIR, "fonts")


def get_imagemagick_path() -> str:
    return _load_config().get("imagemagick_path", "")


def get_llm_provider() -> str:
    return _load_config().get("llm_provider", "gemini")


def get_gemini_model() -> str:
    return _load_config().get("gemini_model", "gemini-2.5-flash")


def get_gemini_models() -> list[str]:
    models = _load_config().get("gemini_models", [])
    if models:
        return models
    return [get_gemini_model()]


def get_pollinations_text_model() -> str:
    return _load_config().get("pollinations_text_model", "openai")


def get_tts_provider() -> str:
    return _load_config().get("tts_provider", "edge_tts")


def get_tts_language() -> str:
    return _load_config().get("tts_language", "es")


def get_tts_speaker_wav() -> str:
    """Reference audio (6-30s WAV/MP3) for voice cloning in XTTS/OpenVoice."""
    configured = _load_config().get("tts_speaker_wav", "")
    if configured and not os.path.isabs(configured):
        return os.path.join(ROOT_DIR, configured)
    return configured


def get_xtts_model() -> str:
    return _load_config().get("xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2")


def get_xtts_device() -> str:
    return _load_config().get("xtts_device", "auto")


def get_openvoice_base_speaker() -> str:
    """ID of MeloTTS base speaker for OpenVoice v2 (e.g. 'ES', 'EN-Default')."""
    return _load_config().get("openvoice_base_speaker", "ES")


def get_openvoice_checkpoints_dir() -> str:
    configured = _load_config().get("openvoice_checkpoints_dir", "")
    if configured and not os.path.isabs(configured):
        return os.path.join(ROOT_DIR, configured)
    return configured or os.path.join(ROOT_DIR, "models", "openvoice_v2")


def get_series() -> list:
    return _load_config().get("series", []) or []


def resolve_series(subject: str):
    if not subject:
        return None, subject
    import re as _re
    m = _re.match(r"^\s*\[([a-zA-Z0-9_\-]+)\]\s*(.*)$", subject)
    if not m:
        return None, subject
    series_id = m.group(1).strip().lower()
    cleaned = m.group(2).strip()
    for s in get_series():
        if str(s.get("id", "")).strip().lower() == series_id:
            return s, (cleaned or subject)
    return None, subject


def get_movie_max_duration_seconds() -> int:
    return int(_load_config().get("movie_max_duration_seconds", 1200))


def get_movie_min_clip_seconds() -> int:
    return int(_load_config().get("movie_min_clip_seconds", 12))


def get_movie_max_clip_seconds() -> int:
    return int(_load_config().get("movie_max_clip_seconds", 45))


def get_movie_hook_seconds() -> int:
    return int(_load_config().get("movie_hook_seconds", 15))


def get_movie_chunk_minutes() -> int:
    return int(_load_config().get("movie_chunk_minutes", 25))


def get_movie_original_audio_volume() -> float:
    return float(_load_config().get("movie_original_audio_volume", 0.08))


def get_movie_download_format() -> str:
    return _load_config().get(
        "movie_download_format",
        "bestvideo[height<=720]+bestaudio/best[height<=720]",
    )


def get_script_sentence_length() -> int:
    val = _load_config().get("script_sentence_length")
    return val if val is not None else 4
