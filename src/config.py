import os
import sys
import json
import shutil
import srt_equalizer

from termcolor import colored

ROOT_DIR = os.path.dirname(sys.path[0])

def assert_folder_structure() -> None:
    """
    Make sure that the nessecary folder structure is present.

    Returns:
        None
    """
    # Create the .mp folder
    if not os.path.exists(os.path.join(ROOT_DIR, ".mp")):
        if get_verbose():
            print(colored(f"=> Creating .mp folder at {os.path.join(ROOT_DIR, '.mp')}", "green"))
        os.makedirs(os.path.join(ROOT_DIR, ".mp"))

def get_first_time_running() -> bool:
    """
    Checks if the program is running for the first time by checking if .mp folder exists.

    Returns:
        exists (bool): True if the program is running for the first time, False otherwise
    """
    return not os.path.exists(os.path.join(ROOT_DIR, ".mp"))

def get_email_credentials() -> dict:
    """
    Gets the email credentials from the config file.

    Returns:
        credentials (dict): The email credentials
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["email"]

def get_verbose() -> bool:
    """
    Gets the verbose flag from the config file.

    Returns:
        verbose (bool): The verbose flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["verbose"]

def get_firefox_profile_path() -> str:
    """
    Gets the path to the Firefox profile.

    Returns:
        path (str): The path to the Firefox profile
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["firefox_profile"]

def get_headless() -> bool:
    """
    Gets the headless flag from the config file.

    Returns:
        headless (bool): The headless flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["headless"]

def get_ollama_base_url() -> str:
    """
    Gets the Ollama base URL.

    Returns:
        url (str): The Ollama base URL
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("ollama_base_url", "http://127.0.0.1:11434")

def get_ollama_model() -> str:
    """
    Gets the primary Ollama model name from the config file.

    Returns:
        model (str): The Ollama model name, or empty string if not set.
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("ollama_model", "")

def get_ollama_models() -> list[str]:
    """
    Ordered list of Ollama models tried by the default text pipeline.
    Each model is tried in order; failure cascades to the next. Falls back
    to ``[get_ollama_model()]`` for backward compatibility with older
    configs that only define the singular field.
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        models = json.load(file).get("ollama_models", [])
    if models:
        return [m for m in models if m]
    primary = get_ollama_model()
    return [primary] if primary else []

def get_long_video_llm_model() -> str:
    """
    Primary Ollama model used by the long-video pipeline.
    Defaults to DeepSeek V4 Pro on Ollama Cloud (`ollama signin` required).
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("long_video_llm_model", "deepseek-v4-pro:cloud")

def get_long_video_llm_models() -> list[str]:
    """
    Ordered list of Ollama models tried by the long-video pipeline.
    Each model is tried in order; failure cascades to the next, and only
    after all entries fail does the LLM layer fall back to Gemini.
    Falls back to ``[get_long_video_llm_model()]`` if not set.
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        models = json.load(file).get("long_video_llm_models", [])
    if models:
        return [m for m in models if m]
    primary = get_long_video_llm_model()
    return [primary] if primary else []

def get_twitter_language() -> str:
    """
    Gets the Twitter language from the config file.

    Returns:
        language (str): The Twitter language
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["twitter_language"]


def get_threads() -> int:
    """
    Gets the amount of threads to use for example when writing to a file with MoviePy.

    Returns:
        threads (int): Amount of threads
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["threads"]

def _get_config_value(name: str, default=None):
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get(name, default)

def _get_bool_config(name: str, default: bool) -> bool:
    value = os.environ.get(f"MP_{name.upper()}", "")
    if not value:
        value = _get_config_value(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def get_short_render_profile() -> str:
    """
    Gets the short-video render profile.

    Only the "quality" profile is supported (Ken Burns + karaoke). The legacy
    "fast" and "turbo" profiles were removed; this always returns "quality".
    """
    return "quality"

def get_short_render_fps() -> int:
    """
    Gets the FPS used when rendering Shorts.
    Lower FPS reduces MoviePy's per-frame Python work.
    """
    default = 60
    value = os.environ.get("MP_SHORT_RENDER_FPS", "").strip()
    if not value:
        value = _get_config_value("short_render_fps", default)
    try:
        fps = int(value)
    except (TypeError, ValueError):
        fps = default
    return max(12, min(60, fps))

def _parse_render_size(value, default: tuple[int, int]) -> tuple[int, int]:
    """Parse render sizes from config values such as "2160x3840" or [2160, 3840]."""
    width, height = default
    try:
        if isinstance(value, dict):
            width = int(value.get("width", width))
            height = int(value.get("height", height))
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            width = int(value[0])
            height = int(value[1])
        elif value:
            text = str(value).strip().lower().replace(" ", "").replace("×", "x")
            if text not in {"4k", "uhd", "ultrahd", "ultra-hd"} and "x" in text:
                raw_width, raw_height = text.split("x", 1)
                width = int(raw_width)
                height = int(raw_height)
    except (TypeError, ValueError):
        width, height = default

    if width < 256 or height < 256:
        return default
    return min(width, 7680), min(height, 7680)

def get_short_render_size() -> tuple[int, int]:
    """Gets the output canvas for Shorts. Defaults to vertical 4K (2160x3840)."""
    default = (2160, 3840)
    value = os.environ.get("MP_SHORT_RENDER_SIZE", "").strip()
    if not value:
        value = _get_config_value("short_render_size", default)
    return _parse_render_size(value, default)

def get_long_render_size() -> tuple[int, int]:
    """Gets the output canvas for long videos. Defaults to landscape 4K (3840x2160)."""
    default = (3840, 2160)
    value = os.environ.get("MP_LONG_RENDER_SIZE", "").strip()
    if not value:
        value = _get_config_value("long_render_size", default)
    return _parse_render_size(value, default)

def get_long_render_fps() -> int:
    """Gets the FPS used when rendering long videos."""
    default = 60
    value = os.environ.get("MP_LONG_RENDER_FPS", "").strip()
    if not value:
        value = _get_config_value("long_render_fps", default)
    try:
        fps = int(value)
    except (TypeError, ValueError):
        fps = default
    return max(12, min(60, fps))

def get_short_ken_burns_enabled() -> bool:
    """Returns whether Shorts should animate image zooms in MoviePy."""
    return _get_bool_config("short_ken_burns", default=True)

def get_short_karaoke_subtitles_enabled() -> bool:
    """Returns whether Shorts should burn word-level karaoke subtitles."""
    return _get_bool_config("short_karaoke_subtitles", default=True)

def get_short_crossfade_seconds() -> float:
    """Gets crossfade duration between Short images."""
    default = 0.4
    value = os.environ.get("MP_SHORT_CROSSFADE_SECONDS", "").strip()
    if not value:
        value = _get_config_value("short_crossfade_seconds", default)
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = default
    return max(0.0, min(2.0, seconds))

def _get_int_config(name: str, default: int, minimum: int, maximum: int) -> int:
    value = os.environ.get(f"MP_{name.upper()}", "").strip()
    if not value:
        value = _get_config_value(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))

def _get_float_config(name: str, default: float, minimum: float, maximum: float) -> float:
    value = os.environ.get(f"MP_{name.upper()}", "").strip()
    if not value:
        value = _get_config_value(name, default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))

def get_subtitle_font_size(default: int) -> int:
    """Gets the base karaoke subtitle font size before render-size scaling."""
    return _get_int_config("subtitle_font_size", default, 28, 180)

def get_subtitle_position_y(default: int) -> int:
    """Gets the base karaoke subtitle vertical position before render-size scaling."""
    return _get_int_config("subtitle_position_y", default, 0, 4320)

def get_subtitle_max_words_per_group(default: int) -> int:
    """Gets the max words shown together in one karaoke subtitle phrase."""
    return _get_int_config("subtitle_max_words_per_group", default, 1, 10)

def get_subtitle_pause_gap_seconds(default: float = 0.35) -> float:
    """Gets the pause length that starts a new karaoke subtitle phrase."""
    return _get_float_config("subtitle_pause_gap_seconds", default, 0.0, 2.0)

def get_render_codec() -> str:
    """
    Gets the MoviePy/ffmpeg video codec.

    Use "auto" to try hardware H.264 encoders first, falling back to libx264.
    """
    codec = os.environ.get("MP_RENDER_CODEC", "").strip()
    if not codec:
        codec = str(_get_config_value("render_codec", "libx264")).strip()
    return codec or "libx264"

def get_render_preset() -> str:
    """Gets the ffmpeg encoder preset, if configured."""
    preset = os.environ.get("MP_RENDER_PRESET", "").strip()
    if not preset:
        preset = str(_get_config_value("render_preset", "") or "").strip()
    return preset

def get_render_bitrate() -> str:
    """Gets an optional ffmpeg video bitrate override."""
    bitrate = os.environ.get("MP_RENDER_BITRATE", "").strip()
    if not bitrate:
        bitrate = str(_get_config_value("render_bitrate", "") or "").strip()
    return bitrate

def get_loudness_target_lufs() -> float:
    """Target integrated loudness (LUFS) for the final audio mix.

    YouTube normalizes uploads to about -14 LUFS; matching it means our audio
    no longer sounds quiet next to other videos. Returns 0.0 to disable the
    loudnorm pass entirely (some users may prefer their own mastering).
    """
    raw = os.environ.get("MP_LOUDNESS_LUFS", "").strip()
    if not raw:
        raw = _get_config_value("loudness_target_lufs", -14.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return -14.0
    # 0 (or any non-negative) disables; valid broadcast targets are negative.
    if value >= 0.0:
        return 0.0
    # Clamp to a sane range so a typo can't produce a broken filter.
    return max(-24.0, min(-9.0, value))
    
def get_zip_url() -> str:
    """
    Gets the URL to the zip file containing the songs.

    Returns:
        url (str): The URL to the zip file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["zip_url"]

def get_is_for_kids() -> bool:
    """
    Gets the is for kids flag from the config file.

    Returns:
        is_for_kids (bool): The is for kids flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["is_for_kids"]

def get_google_maps_scraper_zip_url() -> str:
    """
    Gets the URL to the zip file containing the Google Maps scraper.

    Returns:
        url (str): The URL to the zip file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["google_maps_scraper"]

def get_google_maps_scraper_niche() -> str:
    """
    Gets the niche for the Google Maps scraper.

    Returns:
        niche (str): The niche
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["google_maps_scraper_niche"]

def get_scraper_timeout() -> int:
    """
    Gets the timeout for the scraper.

    Returns:
        timeout (int): The timeout
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["scraper_timeout"] or 300

def get_outreach_message_subject() -> str:
    """
    Gets the outreach message subject.

    Returns:
        subject (str): The outreach message subject
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["outreach_message_subject"]
    
def get_outreach_message_body_file() -> str:
    """
    Gets the outreach message body file.

    Returns:
        file (str): The outreach message body file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["outreach_message_body_file"]

def get_tts_voice() -> str:
    """
    Gets the TTS voice from the config file.

    Returns:
        voice (str): The TTS voice
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("tts_voice", "Jasper")

def get_assemblyai_api_key() -> str:
    """
    Gets the AssemblyAI API key.

    Returns:
        key (str): The AssemblyAI API key
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["assembly_ai_api_key"]

def get_pexels_api_key() -> str:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("pexels_api_key", "")
        return configured or os.environ.get("PEXELS_API_KEY", "")

def get_pixabay_api_key() -> str:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("pixabay_api_key", "")
        return configured or os.environ.get("PIXABAY_API_KEY", "")

def get_europeana_api_key() -> str:
    """Europeana cultural-heritage archive (free key from https://pro.europeana.eu)."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("europeana_api_key", "")
        return configured or os.environ.get("EUROPEANA_API_KEY", "")

def get_ideogram_api_key() -> str:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("ideogram_api_key", "")
        return configured or os.environ.get("IDEOGRAM_API_KEY", "")

def get_leonardo_api_key() -> str:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("leonardo_api_key", "")
        return configured or os.environ.get("LEONARDO_API_KEY", "")

def get_hf_api_key() -> str:
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("hf_api_key", "")
        return configured or os.environ.get("HF_TOKEN", "")

def get_stt_provider() -> str:
    """
    Gets the configured STT provider.

    Returns:
        provider (str): The STT provider
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("stt_provider", "local_whisper")

def get_whisper_model() -> str:
    """
    Gets the local Whisper model name.

    Returns:
        model (str): Whisper model name
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("whisper_model", "base")

def get_whisper_device() -> str:
    """
    Gets the target device for Whisper inference.

    Returns:
        device (str): Whisper device
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("whisper_device", "auto")

def get_whisper_compute_type() -> str:
    """
    Gets the compute type for Whisper inference.

    Returns:
        compute_type (str): Whisper compute type
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("whisper_compute_type", "int8")
    
def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
    """
    Equalizes the subtitles in a SRT file.

    Args:
        srt_path (str): The path to the SRT file
        max_chars (int): The maximum amount of characters in a subtitle

    Returns:
        None
    """
    srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)
    
def get_font() -> str:
    """
    Gets the font from the config file.

    Returns:
        font (str): The font
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["font"]

def get_fonts_dir() -> str:
    """
    Gets the fonts directory.

    Returns:
        dir (str): The fonts directory
    """
    return os.path.join(ROOT_DIR, "fonts")

def get_imagemagick_path() -> str:
    """
    Gets the path to ImageMagick.

    Returns:
        path (str): The path to ImageMagick
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file)["imagemagick_path"]

def get_llm_provider() -> str:
    """Gets the LLM provider (ollama, pollinations, gemini, openai, or claude)."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("llm_provider", "gemini")


def _resolve_cli_command(value: str, default_name: str) -> str:
    """Resolve npm-style CLI shims on Windows while keeping explicit paths."""
    value = (value or default_name).strip() or default_name
    candidates = []
    root, ext = os.path.splitext(value)
    if not ext:
        candidates.extend([f"{value}.cmd", f"{value}.exe", value])
    candidates.append(value)

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        npm_dir = os.path.join(appdata, "npm")
        base = os.path.basename(root or value)
        candidates.extend([
            os.path.join(npm_dir, f"{base}.cmd"),
            os.path.join(npm_dir, f"{base}.exe"),
            os.path.join(npm_dir, base),
        ])

    localappdata = os.environ.get("LOCALAPPDATA", "")
    base_name = os.path.basename(root or value).lower()
    if localappdata and base_name == "codex":
        candidates.append(os.path.join(localappdata, "OpenAI", "Codex", "bin", "codex.exe"))

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if os.path.isfile(candidate):
            return candidate
    return value


def get_openai_base_url() -> str:
    """Gets the OpenAI-compatible API base URL."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("openai_base_url", "")
        return configured or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


def get_openai_api_key() -> str:
    """Gets the OpenAI API key for GPT text generation."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        configured = json.load(file).get("openai_api_key", "")
        return configured or os.environ.get("OPENAI_API_KEY", "")


def get_openai_use_codex_cli() -> bool:
    """Returns whether the OpenAI provider should delegate text calls to Codex CLI."""
    return _get_bool_config("openai_use_codex_cli", False)


def get_codex_cli_command() -> str:
    """Gets the Codex CLI executable used when OpenAI is routed through Codex."""
    value = os.environ.get("MP_CODEX_CLI_COMMAND", "").strip()
    if not value:
        value = str(_get_config_value("codex_cli_command", "codex") or "").strip()
    return _resolve_cli_command(value, "codex")


def get_claude_cli_command() -> str:
    """Gets the Claude CLI executable used by the Claude provider."""
    value = os.environ.get("MP_CLAUDE_CLI_COMMAND", "").strip()
    if not value:
        value = str(_get_config_value("claude_cli_command", "claude") or "").strip()
    return _resolve_cli_command(value, "claude")


def get_claude_cli_model() -> str:
    """Gets the primary Claude CLI model/alias."""
    value = os.environ.get("MP_CLAUDE_CLI_MODEL", "").strip()
    if not value:
        value = str(_get_config_value("claude_cli_model", "") or "").strip()
    return value or "sonnet"


def get_claude_cli_models() -> list[str]:
    """Gets the ordered Claude CLI models/aliases to expose and try."""
    override = os.environ.get("MP_CLAUDE_CLI_MODEL", "").strip()
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        models = json.load(file).get("claude_cli_models", [])
    if override:
        return [override] + [m for m in (models or []) if m != override]
    if models:
        return [m for m in models if m]
    return [get_claude_cli_model()]


def get_claude_cli_timeout_seconds() -> int:
    """Gets the timeout for a single Claude CLI text-generation call."""
    value = os.environ.get("MP_CLAUDE_CLI_TIMEOUT_SECONDS", "").strip()
    if not value:
        value = _get_config_value("claude_cli_timeout_seconds", 300)
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 300
    return max(30, min(3600, seconds))


def get_codex_cli_model() -> str:
    """Gets an optional Codex CLI model override; empty means Codex default."""
    value = os.environ.get("MP_CODEX_CLI_MODEL", "").strip()
    if not value:
        value = str(_get_config_value("codex_cli_model", "") or "").strip()
    return value


def get_codex_cli_sandbox() -> str:
    """Gets the sandbox mode for non-interactive Codex CLI text calls."""
    value = os.environ.get("MP_CODEX_CLI_SANDBOX", "").strip()
    if not value:
        value = str(_get_config_value("codex_cli_sandbox", "read-only") or "").strip()
    if value not in {"read-only", "workspace-write", "danger-full-access"}:
        return "read-only"
    return value


def get_codex_cli_timeout_seconds() -> int:
    """Gets the timeout for a single Codex CLI text-generation call."""
    value = os.environ.get("MP_CODEX_CLI_TIMEOUT_SECONDS", "").strip()
    if not value:
        value = _get_config_value("codex_cli_timeout_seconds", 300)
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 300
    return max(30, min(3600, seconds))


def get_codex_cli_generate_images() -> bool:
    """Returns whether Codex CLI should be tried first for generated visuals."""
    return _get_bool_config("codex_cli_generate_images", True)


def get_codex_cli_image_sandbox() -> str:
    """Gets the sandbox mode for Codex CLI image-generation calls."""
    value = os.environ.get("MP_CODEX_CLI_IMAGE_SANDBOX", "").strip()
    if not value:
        value = str(_get_config_value("codex_cli_image_sandbox", "workspace-write") or "").strip()
    if value not in {"read-only", "workspace-write", "danger-full-access"}:
        return "workspace-write"
    if value == "read-only":
        return "workspace-write"
    return value


def get_codex_cli_image_timeout_seconds() -> int:
    """Gets the timeout for a single Codex CLI visual-generation call."""
    value = os.environ.get("MP_CODEX_CLI_IMAGE_TIMEOUT_SECONDS", "").strip()
    if not value:
        value = _get_config_value("codex_cli_image_timeout_seconds", 900)
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = 900
    return max(60, min(3600, seconds))


def get_image_provider() -> str:
    """Gets the preferred AI image provider: auto, leonardo, openai, or gemini."""
    value = os.environ.get("MP_IMAGE_PROVIDER", "").strip().lower()
    if not value:
        value = str(_get_config_value("image_provider", "auto") or "").strip().lower()
    if value not in {"auto", "leonardo", "openai", "gemini"}:
        return "auto"
    return value


def get_photo_vision_provider() -> str:
    """Gets the preferred uploaded-photo vision backend."""
    value = os.environ.get("MP_PHOTO_VISION_PROVIDER", "").strip().lower()
    if not value:
        value = str(_get_config_value("photo_vision_provider", "auto") or "").strip().lower()
    aliases = {
        "codex_cli": "codex",
        "codex-cli": "codex",
        "claude_cli": "claude",
        "claude-cli": "claude",
        "openai_api": "openai",
        "openai-api": "openai",
    }
    value = aliases.get(value, value)
    if value not in {"auto", "gemini", "codex", "claude", "openai"}:
        return "auto"
    return value


def get_nanobanana2_api_base_url() -> str:
    """Gets the Gemini/Nano Banana API base URL."""
    value = str(_get_config_value("nanobanana2_api_base_url", "") or "").strip()
    return value or os.environ.get("NANOBANANA2_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


def get_nanobanana2_api_key() -> str:
    """Gets the Nano Banana image API key, falling back to Gemini credentials."""
    configured = str(_get_config_value("nanobanana2_api_key", "") or "").strip()
    return (
        configured
        or os.environ.get("NANOBANANA2_API_KEY", "")
        or get_gemini_api_key()
        or os.environ.get("GEMINI_API_KEY", "")
    )


def get_nanobanana2_model() -> str:
    """Gets the Gemini native image model used for Nano Banana images."""
    value = str(_get_config_value("nanobanana2_model", "") or "").strip()
    return value or os.environ.get("NANOBANANA2_MODEL", "gemini-2.5-flash-image")


def get_nanobanana2_aspect_ratio() -> str:
    """Gets the requested aspect ratio for Nano Banana images."""
    value = str(_get_config_value("nanobanana2_aspect_ratio", "") or "").strip()
    value = os.environ.get("NANOBANANA2_ASPECT_RATIO", value).strip() or "9:16"
    if value not in {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}:
        return "9:16"
    return value


def get_openai_model() -> str:
    """Gets the primary OpenAI model for text generation."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("openai_model", "gpt-5.5")


def get_openai_models() -> list[str]:
    """Gets the ordered list of OpenAI models to try (best first)."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        models = json.load(file).get("openai_models", [])

    override = os.environ.get("MP_OPENAI_MODEL_OVERRIDE", "").strip()
    if override:
        models = [override] + [m for m in (models or []) if m != override]
        return models

    if models:
        return models
    return [get_openai_model()]


def get_openai_reasoning_effort() -> str:
    """Gets the reasoning effort used for GPT-5/OpenAI reasoning models."""
    value = os.environ.get("MP_OPENAI_REASONING_EFFORT", "").strip()
    if not value:
        with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
            value = str(json.load(file).get("openai_reasoning_effort", "medium")).strip()
    value = (value or "medium").lower()
    if value not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return "medium"
    return value


def get_pollinations_text_model() -> str:
    """Gets the configured Pollinations text model (default: openai)."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("pollinations_text_model", "openai")

def get_gemini_model() -> str:
    """Gets the primary Gemini model for text generation."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("gemini_model", "gemini-2.5-flash")

def get_gemini_models() -> list[str]:
    """Gets the ordered list of Gemini models to try (best first).

    Per-job override via MP_GEMINI_MODEL_OVERRIDE pushes the chosen model to
    the front of the list (and falls back to the configured ones if it gets
    rate-limited) — set by the webapp runner when the user picks a specific
    model in the Generate UI."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        models = json.load(file).get("gemini_models", [])

    override = os.environ.get("MP_GEMINI_MODEL_OVERRIDE", "").strip()
    if override:
        models = [override] + [m for m in (models or []) if m != override]
        return models

    if models:
        return models
    # Fallback: just the single configured model
    return [get_gemini_model()]

def get_gemini_api_key() -> str:
    """Gets the Gemini API key for LLM text generation."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("gemini_api_key", "")

def get_tts_provider() -> str:
    """Gets the TTS provider (edge_tts or kittentts)."""
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("tts_provider", "edge_tts")

def get_series() -> list:
    """
    Gets the list of series defined in config.json. Each series is a dict with:
      - id (str): unique identifier (e.g. "un_dia_en_la_historia")
      - title_template (str): template with {placeholders} the LLM will fill
      - thumbnail_overlay (str): exact text stamped on the thumbnail (no LLM)
      - thumbnail_font (str, optional): font filename to look up in Windows Fonts

    Returns:
        series (list): list of series dicts, or [] if none configured.
    """
    # utf-8 here so users can paste accented chars (á, é, í, ó, ú, ñ) literally
    # into title_template / thumbnail_overlay without re-encoding the file.
    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        return json.load(file).get("series", []) or []


def resolve_series(subject: str):
    """
    If `subject` starts with a `[series_id]` prefix that matches a configured
    series, return (series_dict, cleaned_subject). Otherwise return (None, subject).

    Example:
        "[un_dia_en_la_historia] samurai en el Japón feudal"
        → ({"id": "un_dia_en_la_historia", ...}, "samurai en el Japón feudal")
    """
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


def get_script_sentence_length() -> int:
    """
    Gets the forced script's sentence length.

    Per-job overrides via the MP_SENTENCE_LENGTH_OVERRIDE env var win over the
    config file — the webapp uses this to let users pick an estimated
    duration without mutating config.json shared across other jobs.

    Returns:
        length (int): Length of script's sentence
    """
    override = os.environ.get("MP_SENTENCE_LENGTH_OVERRIDE", "").strip()
    if override:
        try:
            n = int(override)
            if n > 0:
                return n
        except ValueError:
            pass

    with open(os.path.join(ROOT_DIR, "config.json"), "r", encoding="utf-8") as file:
        config_json = json.load(file)
        if (config_json.get("script_sentence_length") is not None):
            return config_json["script_sentence_length"]
        else:
            return 4


def get_winner_remix_enabled() -> bool:
    """Returns whether the Winner Remix flow is allowed to fire."""
    return _get_bool_config("winner_remix_enabled", default=True)


def get_winner_remix_ratio() -> int:
    """Cadence for Winner Remix: roughly 1 remix every N videos (default 6)."""
    return _get_int_config("winner_remix_ratio", default=6, minimum=2, maximum=100)


def get_winner_remix_min_views() -> int:
    """Minimum view count for a video to qualify as a remix source."""
    return _get_int_config("winner_remix_min_views", default=1000, minimum=1, maximum=100000000)


def get_long_ctr_enabled() -> bool:
    """CTR packaging for long videos: scored title candidates + chapters."""
    return _get_bool_config("long_ctr_enabled", default=True)


def get_long_retention_enabled() -> bool:
    """Retention gate for long-form scripts (score + intro rewrite)."""
    return _get_bool_config("long_retention_enabled", default=True)


def get_thumbnail_lab_candidates() -> int:
    """How many thumbnail backgrounds to generate and score (1 = disabled).

    Each extra candidate costs one image-generation call, so the default
    stays modest. The best-scoring background wins per ThumbnailLab."""
    return _get_int_config("thumbnail_lab_candidates", default=3, minimum=1, maximum=6)


def get_learning_enabled() -> bool:
    """Returns whether the LearningCoach reflects after a YouTube sync."""
    return _get_bool_config("learning_enabled", default=True)


def get_learning_max_lessons() -> int:
    """Maximum natural-language lessons kept in a channel's learning memory."""
    return _get_int_config("learning_max_lessons", default=30, minimum=5, maximum=200)


def get_learning_model() -> str:
    """Optional Claude CLI model/alias for reflection. Empty uses the default."""
    value = os.environ.get("MP_LEARNING_MODEL", "").strip()
    if not value:
        value = str(_get_config_value("learning_model", "") or "").strip()
    return value
