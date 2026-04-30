# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MoneyPrinterV2 (MPV2) is a Python 3.12 CLI tool that automates four online workflows:
1. **YouTube Shorts** — generate video (LLM script → TTS → images → MoviePy composite) and upload via Selenium
2. **Twitter/X Bot** — generate and post tweets via Selenium
3. **Affiliate Marketing** — scrape Amazon product info, generate pitch, share on Twitter
4. **Local Business Outreach** — scrape Google Maps (Go binary), extract emails, send cold outreach via SMTP

There is no web UI, no REST API, no test suite, no CI, and no linting config.

## Running the Application

```bash
# First-time setup
cp config.example.json config.json   # then fill in values
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# macOS quick setup (auto-configures Ollama, ImageMagick, Firefox profile)
bash scripts/setup_local.sh

# Preflight check (validates services are reachable)
python scripts/preflight_local.py

# Run
python src/main.py
```

The app **must** be run from the project root. `python src/main.py` adds `src/` to `sys.path`, so all imports use bare module names (e.g., `from config import *`, not `from src.config import *`).

## Architecture

### Entry Points
- `src/main.py` — interactive menu loop (primary)
- `src/cron.py` — headless runner invoked by the scheduler as a subprocess: `python src/cron.py <platform> <account_uuid>`

### Provider Pattern
Two service categories use a string-based dispatch pattern configured in `config.json`:

| Category | Config key | Options |
|---|---|---|
| LLM | `ollama_model` | Ollama (via `ollama` Python SDK). If empty, user picks from available models at startup. |
| Image gen | — | `nanobanana2` (Gemini image API) |
| STT | `stt_provider` | `local_whisper`, `third_party_assemblyai` |

LLM always uses the local Ollama server. Image generation always uses Nano Banana 2.

### Key Modules
- **`src/llm_provider.py`** — unified `generate_text(prompt)` function using the Ollama Python SDK
- **`src/config.py`** — 30+ getter functions, each re-reads `config.json` on every call (no caching). `ROOT_DIR` = project root, computed as `os.path.dirname(sys.path[0])`
- **`src/cache.py`** — JSON file persistence in `.mp/` directory (accounts, videos, posts, products)
- **`src/constants.py`** — menu strings, Selenium selectors (YouTube Studio, X.com, Amazon)
- **`src/classes/YouTube.py`** — most complex class; full pipeline: topic → script → metadata → image prompts → images → TTS → subtitles → MoviePy combine → Selenium upload
- **`src/classes/Twitter.py`** — Selenium automation against x.com
- **`src/classes/AFM.py`** — Amazon scraping + LLM pitch generation
- **`src/classes/Outreach.py`** — Google Maps scraper (requires Go) + email sending via yagmail
- **`src/classes/Tts.py`** — KittenTTS wrapper

### Data Storage
All persistent state lives in `.mp/` at the project root as JSON files (`youtube.json`, `twitter.json`, `afm.json`). This directory also serves as scratch space for temporary WAV, PNG, SRT, and MP4 files — non-JSON files are cleaned on each run by `rem_temp_files()`.

### Browser Automation
Selenium uses pre-authenticated Firefox profiles (never handles login). The profile path is stored per-account in the cache JSON and also in `config.json` as a default.

### CRON Scheduling
Uses Python's `schedule` library (in-process, not OS cron). The scheduled job spawns `subprocess.run(["python", "src/cron.py", platform, account_id])`.

## Configuration

All config lives in `config.json` at the project root. See `config.example.json` for the full template and `docs/Configuration.md` for reference. Key external dependencies to configure:
- **ImageMagick** — required for MoviePy subtitle rendering (`imagemagick_path`)
- **Firefox profile** — must be pre-logged-in to target platforms (`firefox_profile`)
- **Ollama** — for LLM text generation (via `ollama` Python SDK)
- **Nano Banana 2** — for image generation (Gemini image API)
- **Go** — only needed for Outreach (Google Maps scraper)

## Contributing

PRs go against `main`. One feature/fix per PR. Open an issue first. Use `WIP` label for in-progress PRs.

## Upstream merge policy (`andre` remote → `andrepichardo/MoneyPrinterV2`)

This fork has diverged significantly. **Never run `git merge andre/main` blindly** — the upstream is on a simplification trajectory that deletes features we depend on. Cherry-pick only.

### Channel context (drives the policy)

The active YouTube channel niche is **Universo / astronomía** (e.g. agujeros negros, supernovas, paradoja de Olbers). Movie Summary builds on top of that. There is no history-channel use case in this repo, so changes scoped to ancient civilizations are useless overhead here.

### What we have that upstream is removing — DO NOT let a merge delete these

- `scripts/peek_inspiration.py` — used to seed topics from external content
- `scripts/video_from_inspiration.py` — full inspiration-driven pipeline
- `src/inspire.py` — the inspiration module
- `src/config.py::get_long_video_llm_model()` — required by Movie Summary; upstream deleted it
- Large chunks of `src/utils.py` and `src/llm_provider.py` (we have the more complete versions)
- The entire Movie Summary stack we built locally (`MovieSummary.py`, `MovieCatalog.py`, `ImdbIndex.py`) — upstream doesn't know about these

### What's safe to cherry-pick from upstream

As of the last audit (commits `e321e5f` and earlier), **nothing**. Every change in those 7 commits is one of:
- History-niche specific (era anchoring via `name`/`era_brief` fields on `CIVILIZATION_ART_STYLES`, the era-clause injection in `generate_long_prompts`, the 3 historical example scenes in the prompt) — irrelevant for the Universo niche, and the historical examples actively bias the LLM toward the wrong visuals
- Already in our code in a more complete form (`SONG_KEYWORDS`, `choose_random_song`, song history) — our `utils.py` has these plus extras
- A subset of forbidden-words lists we already have (we have the bigger list)

### When we WOULD cherry-pick

Re-audit the upstream only if one of:
- We start a history channel (era anchoring becomes valuable)
- Upstream lands a substantively new feature that's not in this list of "already have / not applicable"

To audit safely:
```bash
git fetch andre
git log HEAD..andre/main --oneline
git diff HEAD..andre/main -- src/classes/YouTube.py
```
Apply changes by hand, never `git cherry-pick` the whole commit (their commits are titled "Update YouTube.py" with no body and bundle multiple unrelated edits).
