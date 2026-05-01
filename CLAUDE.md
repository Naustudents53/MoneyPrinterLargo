# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MoneyPrinterLargo is a Python 3.12 CLI tool that automates five online workflows:
1. **YouTube Shorts & Long Video** — generate video (LLM script → TTS → images → MoviePy composite) and upload via Selenium
2. **Twitter/X Bot** — generate and post tweets via Selenium
3. **Affiliate Marketing** — scrape Amazon product info, generate pitch, share on Twitter
4. **Local Business Outreach** — scrape Google Maps (Go binary), extract emails, send cold outreach via SMTP
5. **Movie Summary** — download public-domain films, transcribe, cut clips, narrate, composite recap videos

There is also a **Next.js 16 web dashboard** in `studio/` with React 19, Tailwind CSS 4, Radix UI, Framer Motion, and Zustand.

## Agent Configuration

This project has 5 specialized agents in `.claude/agents/`. Delegate work to them via the Task tool:

| Agent | Use for |
|-------|---------|
| **qa-engineer** | Writing tests (pytest, Playwright), code quality reviews, coverage checks |
| **devops-engineer** | Docker, CI/CD, GitHub Actions, infrastructure setup |
| **ux-ui-designer** | Dashboard design, component aesthetics, accessibility, video thumbnails |
| **backend-developer** | Python CLI modules, YouTube/Twitter/Movie pipelines, LLM providers, Selenium |
| **frontend-developer** | Next.js 16 dashboard with React 19, Radix UI, Zustand stores |

## Running the Application

```bash
# First-time setup
cp config.example.json config.json   # then fill in values
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# macOS/Linux quick setup (auto-configures Ollama, ImageMagick, Firefox profile)
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
| LLM | `llm_provider` | `gemini`, `ollama`, `pollinations` (cascading fallback) |
| Image gen | — | `nanobanana2` (Gemini image API) |
| STT | `stt_provider` | `local_whisper`, `assemblyai` |

### Key Modules
- **`src/llm_provider.py`** — unified `generate_text(prompt)` with cascading fallback across 3 providers
- **`src/config.py`** — 30+ getter functions with lazy-loaded caching, env var fallbacks. `ROOT_DIR` = project root
- **`src/cache.py`** — JSON file persistence in `.mp/` directory (accounts, videos, posts, products)
- **`src/constants.py`** — menu strings, Selenium selectors (YouTube Studio, X.com, Amazon)
- **`src/classes/YouTube.py`** — most complex class (~4365 lines); full pipeline: topic → script → metadata → image prompts → images → TTS → subtitles → MoviePy combine → Selenium upload
- **`src/classes/Twitter.py`** — Selenium automation against x.com
- **`src/classes/AFM.py`** — Amazon scraping + LLM pitch generation
- **`src/classes/Outreach.py`** — Google Maps scraper (requires Go) + email sending via yagmail
- **`src/classes/Tts.py`** — Edge-TTS / KittenTTS wrapper
- **`src/classes/MovieSummary.py`** — end-to-end movie recap pipeline
- **`src/classes/MovieCatalog.py`** — archive.org API catalog browser
- **`src/classes/ImdbIndex.py`** — local IMDb index builder

### Data Storage
All persistent state lives in `.mp/` at the project root as JSON files. This directory also serves as scratch space for temporary WAV, PNG, SRT, and MP4 files — non-JSON files are cleaned on each run.

### Browser Automation
Selenium uses pre-authenticated Firefox profiles (never handles login). The profile path is stored per-account in the cache JSON.

### CRON Scheduling
Uses Python's `schedule` library (in-process). The scheduled job spawns `subprocess.run(["python", "src/cron.py", platform, account_id])`.

## Configuration

All config lives in `config.json` at the project root. See `config.example.json` for the full template and `docs/Configuration.md` for reference. Key external dependencies:
- **ImageMagick** — required for MoviePy subtitle rendering (`imagemagick_path`)
- **Firefox profile** — must be pre-authenticated to target platforms (`firefox_profile`)
- **LLM** — Ollama server, Gemini API, or Pollinations.ai
- **Image gen** — Gemini image API (Nano Banana 2)
- **Go** — only needed for Outreach (Google Maps scraper)

## Testing

```bash
# Run all tests with coverage
python -m pytest tests/ --cov=src --cov-report=term-missing

# Preflight check
python scripts/preflight_local.py
```

Target 80%+ coverage on all new code. Follow TDD workflow (red → green → refactor with git checkpoints).

## Studio Dashboard

```bash
cd studio
npm run dev      # development server
npm run build    # production build
npm run lint     # ESLint check
```

The dashboard uses the Next.js 16 App Router. Read `studio/node_modules/next/dist/docs/` for API guidance as this version has breaking changes.

## Upstream merge policy (`andre` remote → `andrepichardo/MoneyPrinterV2`)

This fork has diverged significantly. **Never run `git merge andre/main` blindly** — cherry-pick only.

## Active channel context

The active YouTube channel niche is **Universo / astronomia** (black holes, supernovas, cosmos documentaries). Movie Summary builds on top of that.

### What we have that upstream is removing — DO NOT let a merge delete these
- `scripts/peek_inspiration.py` — seeds topics from external content
- `scripts/video_from_inspiration.py` — inspiration-driven pipeline
- `src/inspire.py` — inspiration module
- `src/config.py::get_long_video_llm_model()` — required by Movie Summary
- Large chunks of `src/utils.py` and `src/llm_provider.py` (we have the more complete versions)
- The entire Movie Summary stack (`MovieSummary.py`, `MovieCatalog.py`, `ImdbIndex.py`)
