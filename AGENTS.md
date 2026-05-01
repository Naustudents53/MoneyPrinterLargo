# Repository Guidelines

## Project Structure
- `src/` — Python CLI application code. **Run everything from repo root** (`python src/main.py`).
- `src/classes/` — Provider-specific modules: `YouTube.py`, `Twitter.py`, `Tts.py`, `AFM.py`, `Outreach.py`, `MovieSummary.py`, `MovieCatalog.py`, `ImdbIndex.py`.
- `src/compat.py` — **Must be imported first** in any entry-point script. Patches Pillow→MoviePy compatibility and discovers `ffmpeg` on Windows.
- `src/config.py` — 30+ getter functions with lazy caching and env var fallbacks.
- `src/llm_provider.py` — Unified LLM dispatcher (Ollama → Gemini → Pollinations cascading fallback).
- `scripts/` — Helper workflows: `setup_local.sh`, `preflight_local.py`, `upload_video.sh`, `make_thumbnail.py`, etc.
- `studio/` — Next.js 16 dashboard (separate app, own `package.json` and `node_modules`). Has its own `AGENTS.md` with breaking-change warnings.
- `docs/` — Feature docs; `assets/` / `fonts/` — static resources.
- `.mp/` — Runtime JSON cache and scratch space (WAV, PNG, SRT, MP4). Gitignored.

## Specialized Agents
Delegate complex work via the Task tool:

| Agent | File | Role |
|-------|------|------|
| **QA Engineer** | `qa-engineer.md` | Testing strategy, pytest/Playwright, coverage |
| **DevOps Engineer** | `devops-engineer.md` | Docker, CI/CD, deployment (none exist yet) |
| **UX/UI Designer** | `ux-ui-designer.md` | Dashboard design, thumbnails, accessibility, video aesthetics |
| **Backend Developer** | `backend-developer.md` | Python CLI, pipelines, LLM providers, Selenium |
| **Frontend Developer** | `frontend-developer.md` | Next.js 16 dashboard, React 19, Tailwind CSS 4, Radix UI, Zustand |

**Note for Frontend agent:** When improving UI, apply the `frontend-design` skill for visual direction, typography, and motion.

## Build, Test, and Development Commands

### Python Backend
```bash
# First-time setup (macOS/Linux)
bash scripts/setup_local.sh

# Manual setup (all platforms)
cp config.example.json config.json
python -m venv venv
# Windows: venv\Scripts\activate
# Unix:    source venv/bin/activate
pip install -r requirements.txt

# Validate local readiness
python scripts/preflight_local.py

# Run CLI (must be from repo root)
python src/main.py

# Direct upload script
bash scripts/upload_video.sh
```

### Studio Dashboard
```bash
cd studio
npm install
npm run dev      # port 3000 (Next.js 16, heed deprecation notices)
npm run build
npm run lint     # ESLint via eslint.config.mjs
```

### API Backend (studio/api_server.py)
```bash
# Requires fastapi + uvicorn (install into same venv)
pip install fastapi uvicorn

# Windows
venv\Scripts\activate && cd studio && python api_server.py
# Unix
source venv/bin/activate && cd studio && python api_server.py
# → http://localhost:8000 (CORS allows localhost:3000)
```

## Architecture Quick Reference
- **Entry points:** `src/main.py` (interactive menu), `src/cron.py <platform> <account_uuid> [model]` (headless scheduler subprocess).
- **Import rule:** `main.py` prepends `src/` to `sys.path`. Use bare imports: `from config import *`, **never** `from src.config import *`.
- **Provider dispatch:** LLM (`llm_provider`), Image (`nanobanana2`), STT (`stt_provider: local_whisper | assemblyai`).
- **Browser automation:** Selenium with pre-authenticated Firefox profiles. Profile paths are stored per-account in `.mp/` JSON — **never commit profiles**.
- **Data storage:** All persistent state is JSON in `.mp/` (accounts, videos, posts, products, catalog). Non-JSON temp files are cleaned per run.

## Testing Reality
- **No `tests/` directory exists yet.** The QA agent is responsible for bootstrapping it.
- Target 80 %+ coverage on new code. Use `pytest` with fixtures in `tests/conftest.py` when created.
- `scripts/preflight_local.py` is the current smoke test.

## Coding Style
- Python 3.12, 4-space indent.
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants.
- TypeScript: strict mode, explicit public return types, `camelCase` vars/functions, `PascalCase` components, prefer `interface` over `type`.
- New business logic → focused modules under `src/`. Provider/integration code → `src/classes/`.

## Security & Configuration
- `config.json` is environment-specific and gitignored. Seed from `config.example.json`.
- Prefer env vars where supported (e.g. `GEMINI_API_KEY` for `nanobanana2_api_key`).
- Never log API keys, tokens, or SMTP passwords.
- Selenium Firefox profiles contain session cookies — **never commit them**.

## Merge Policy & Protected Code
This fork diverged significantly from upstream (`andrepichardo/MoneyPrinterV2`).
- **Never run `git merge andre/main` blindly** — cherry-pick only.
- **Do not let upstream merges delete these:**
  - `scripts/peek_inspiration.py`
  - `scripts/video_from_inspiration.py`
  - `src/inspire.py`
  - `src/config.py::get_long_video_llm_model()`
  - Large chunks of `src/utils.py` and `src/llm_provider.py`
  - Entire Movie Summary stack (`MovieSummary.py`, `MovieCatalog.py`, `ImdbIndex.py`)

## Commit Style
- Imperative summaries: `Fix ...`, `Update ...`, optionally with issue refs (e.g. `(#128)`).
- PRs against `main`, one feature/fix per PR, clear title + description.
- Mark WIP PRs explicitly; remove WIP when ready.
