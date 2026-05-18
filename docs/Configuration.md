# Configuration

All your configurations will be in a file in the root directory, called `config.json`, which is a copy of `config.example.json`. You can change the values in `config.json` to your liking.

## Values

- `verbose`: `boolean` - If `true`, the application will print out more information.
- `firefox_profile`: `string` - The path to your Firefox profile. This is used to use your Social Media Accounts without having to log in every time you run the application.
- `headless`: `boolean` - If `true`, the application will run in headless mode. This means that the browser will not be visible.
- `ollama_base_url`: `string` - Base URL of your local Ollama server (default: `http://127.0.0.1:11434`).
- `ollama_model`: `string` - Ollama model to use for text generation (e.g. `llama3.2:3b`). If empty, the app queries Ollama at startup and lets you pick from the available models interactively.
- `image_provider`: `string` - AI image backend override: `auto`, `leonardo`, `openai` (Codex CLI Image), or `gemini` (Nano Banana).
- `twitter_language`: `string` - The language that will be used to generate & post tweets.
- `nanobanana2_api_base_url`: `string` - Nano Banana 2 API base URL (default: `https://generativelanguage.googleapis.com/v1beta`).
- `gemini_api_key`: `string` - API key for the Gemini API (used for both text generation and Nano Banana 2 image generation). If empty, MPP falls back to environment variable `GEMINI_API_KEY`.
- `openai_api_key`: `string` - API key for the OpenAI Responses API. If empty, MPP falls back to environment variable `OPENAI_API_KEY`.
- `openai_reasoning_effort`: `string` - Default OpenAI/Codex thinking level. Supported values: `low`, `medium`, `high`, `xhigh` (also `none`/`minimal` for advanced CLI/API use). The Generate UI can override this per job when OpenAI is selected.
- `openai_use_codex_cli`: `boolean` - If `true`, selecting `llm_provider: "openai"` delegates text generation to your locally logged-in `codex exec` instead of the OpenAI API key path.
- `codex_cli_command`: `string` - Codex CLI executable name/path used by `openai_use_codex_cli` (default: `codex`).
- `codex_cli_model`: `string` - Optional Codex CLI model override. Leave empty to use the model selected in the UI or Codex's own default.
- `codex_cli_sandbox`: `string` - Codex CLI sandbox for text calls: `read-only`, `workspace-write`, or `danger-full-access`. `read-only` is recommended.
- `codex_cli_timeout_seconds`: `number` - Timeout for each `codex exec` text-generation call.
- `codex_cli_generate_images`: `boolean` - If `true`, selecting OpenAI through Codex CLI also tries Codex CLI first for generated video images and thumbnails.
- `codex_cli_image_sandbox`: `string` - Sandbox for Codex CLI image calls. Must allow writing the generated PNG; `workspace-write` is recommended.
- `codex_cli_image_timeout_seconds`: `number` - Timeout for each image generated through Codex CLI.
- `claude_cli_command`: `string` - Claude CLI executable name/path used when selecting `claude` as LLM provider (default: `claude`).
- `claude_cli_model`: `string` - Default Claude CLI model/alias (default: `sonnet`).
- `claude_cli_models`: `array` - Claude CLI models/aliases shown in the Generate selector.
- `claude_cli_timeout_seconds`: `number` - Timeout for each `claude --print` text-generation call.
- `nanobanana2_model`: `string` - Nano Banana model name (default: `gemini-2.5-flash-image`).
- `nanobanana2_aspect_ratio`: `string` - Aspect ratio for generated images (default: `9:16`).
- `threads`: `number` - The amount of threads that will be used to execute operations, e.g. writing to a file using MoviePy.
- `short_render_profile`: `string` - Short render tradeoff: `quality` keeps Ken Burns + karaoke subtitles, `fast` uses static images + karaoke subtitles, and `turbo` uses static images without burned-in karaoke for maximum render speed.
- `short_render_fps`: `number` - FPS for Shorts rendering. Lower values reduce MoviePy per-frame work; `24` is a good speed/quality default.
- `short_ken_burns`: `boolean` - If `true`, Shorts animate image zooms. This is visually richer but much slower because MoviePy resizes every frame in Python.
- `short_karaoke_subtitles`: `boolean` - If `true`, Shorts burn word-level karaoke subtitles into the video. Disable for the fastest render.
- `short_crossfade_seconds`: `number` - Crossfade overlap between Short images. Use `0` for the fastest concatenation path.
- `render_codec`: `string` - ffmpeg codec used by MoviePy. Use `libx264` for reliable CPU encoding or `auto` to try hardware H.264 encoders before falling back.
- `render_preset`: `string` - Optional ffmpeg preset override. Empty uses `ultrafast` for `libx264` and the encoder default for hardware codecs.
- `render_bitrate`: `string` - Optional video bitrate override, e.g. `8000k`.
- `is_for_kids`: `boolean` - If `true`, the application will upload the video to YouTube Shorts as a video for kids.
- `google_maps_scraper`: `string` - The URL to the Google Maps scraper. This will be used to scrape Google Maps for local businesses. It is recommended to use the default value.
- `zip_url`: `string` - The URL to the ZIP file that contains the to be used Songs for the YouTube Shorts Automater.
- `email`: `object`:
    - `smtp_server`: `string` - Your SMTP server.
    - `smtp_port`: `number` - The port of your SMTP server.
    - `username`: `string` - Your email address.
    - `password`: `string` - Your email password.
- `google_maps_scraper_niche`: `string` - The niche you want to scrape Google Maps for.
- `scraper_timeout`: `number` - The timeout for the Google Maps scraper.
- `outreach_message_subject`: `string` - The subject of your outreach message. `{{COMPANY_NAME}}` will be replaced with the company name.
- `outreach_message_body_file`: `string` - The file that contains the body of your outreach message, should be HTML. `{{COMPANY_NAME}}` will be replaced with the company name.
- `stt_provider`: `string` - Provider for subtitle transcription. Default is `local_whisper`. Options:
    * `local_whisper`
    * `third_party_assemblyai`
- `whisper_model`: `string` - Whisper model for local transcription (for example `base`, `small`, `medium`, `large-v3`).
- `whisper_device`: `string` - Device for local Whisper (`auto`, `cpu`, `cuda`).
- `whisper_compute_type`: `string` - Compute type for local Whisper (`int8`, `float16`, etc.).
- `assembly_ai_api_key`: `string` - Your Assembly AI API key. Get yours from [here](https://www.assemblyai.com/app/).
- `tts_voice`: `string` - Voice for KittenTTS text-to-speech. Default is `Jasper`. Options: `Bella`, `Jasper`, `Luna`, `Bruno`, `Rosie`, `Hugo`, `Kiki`, `Leo`.
- `font`: `string` - The font that will be used to generate images. This should be a `.ttf` file in the `fonts/` directory.
- `imagemagick_path`: `string` - The path to the ImageMagick binary. This is used by MoviePy to manipulate images. Install ImageMagick from [here](https://imagemagick.org/script/download.php) and set the path to the `magick.exe` on Windows, or on Linux/MacOS the path to `convert` (usually /usr/bin/convert).
- `script_sentence_length`: `number` - The number of sentences in the generated video script (default: `4`).

## Example

```json
{
  "verbose": true,
  "firefox_profile": "",
  "headless": false,
  "ollama_base_url": "http://127.0.0.1:11434",
  "ollama_model": "",
  "image_provider": "auto",
  "twitter_language": "English",
  "nanobanana2_api_base_url": "https://generativelanguage.googleapis.com/v1beta",
  "nanobanana2_api_key": "",
  "gemini_api_key": "",
  "openai_api_key": "",
  "openai_reasoning_effort": "medium",
  "openai_use_codex_cli": false,
  "codex_cli_command": "codex",
  "codex_cli_model": "",
  "codex_cli_sandbox": "read-only",
  "codex_cli_timeout_seconds": 300,
  "codex_cli_generate_images": true,
  "codex_cli_image_sandbox": "workspace-write",
  "codex_cli_image_timeout_seconds": 900,
  "claude_cli_command": "claude",
  "claude_cli_model": "sonnet",
  "claude_cli_models": ["sonnet", "opus", "haiku"],
  "claude_cli_timeout_seconds": 300,
  "nanobanana2_model": "gemini-2.5-flash-image",
  "nanobanana2_aspect_ratio": "9:16",
  "threads": 2,
  "short_render_profile": "quality",
  "short_render_fps": 30,
  "short_ken_burns": true,
  "short_karaoke_subtitles": true,
  "short_crossfade_seconds": 0.4,
  "render_codec": "libx264",
  "render_preset": "ultrafast",
  "render_bitrate": "",
  "zip_url": "",
  "is_for_kids": false,
  "google_maps_scraper": "https://github.com/gosom/google-maps-scraper/archive/refs/tags/v0.9.7.zip",
  "email": {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "",
    "password": ""
  },
  "google_maps_scraper_niche": "",
  "scraper_timeout": 300,
  "outreach_message_subject": "I have a question...",
  "outreach_message_body_file": "outreach_message.html",
  "stt_provider": "local_whisper",
  "whisper_model": "base",
  "whisper_device": "auto",
  "whisper_compute_type": "int8",
  "assembly_ai_api_key": "",
  "tts_voice": "Jasper",
  "font": "bold_font.ttf",
  "imagemagick_path": "Path to magick.exe or on linux/macOS just /usr/bin/convert",
  "script_sentence_length": 4
}
```

## Environment Variable Fallbacks

- `GEMINI_API_KEY`: used when `gemini_api_key` is empty.
- `OPENAI_API_KEY`: used when `openai_api_key` is empty and `openai_use_codex_cli` is `false`.
- `MP_OPENAI_USE_CODEX_CLI`: set to `true` to route the OpenAI provider through `codex exec` without editing `config.json`.
- `MP_CODEX_CLI_COMMAND`, `MP_CODEX_CLI_MODEL`, `MP_CODEX_CLI_SANDBOX`, `MP_CODEX_CLI_TIMEOUT_SECONDS`: override Codex CLI settings.
- `MP_CODEX_CLI_IMAGE_SANDBOX`, `MP_CODEX_CLI_IMAGE_TIMEOUT_SECONDS`: override Codex CLI image settings.

Example:

```bash
export GEMINI_API_KEY="your_api_key_here"
```
