# Repository Guidelines

## Project Structure & Module Organization
- `src/` contains the application code. Use `src/main.py` as the interactive entrypoint.
- `src/classes/` holds provider-specific components (for example `YouTube.py`, `Twitter.py`, `Tts.py`, `AFM.py`, `Outreach.py`).
- Shared utilities and configuration live in modules like `src/config.py`, `src/utils.py`, `src/cache.py`, and `src/constants.py`.
- `scripts/` contains helper workflows such as setup, preflight checks, and upload helpers.
- `docs/` contains feature documentation; `assets/` and `fonts/` contain static resources.
- `studio/` is a Next.js 16 web dashboard (separate app with its own package.json and node_modules).

## Specialized Agent Configuration
This project has 5 purpose-built agents in `.claude/agents/`:

| Agent | File | Role |
|-------|------|------|
| **QA Engineer** | `qa-engineer.md` | Testing (pytest, Playwright), code quality, coverage enforcement |
| **DevOps Engineer** | `devops-engineer.md` | Docker, CI/CD, deployment, infrastructure |
| **UX/UI Designer** | `ux-ui-designer.md` | Dashboard design, component aesthetics, accessibility, video thumbnails |
| **Backend Developer** | `backend-developer.md` | Python CLI, YouTube/Twitter/Outreach pipelines, LLM providers, Selenium |
| **Frontend Developer** | `frontend-developer.md` | Next.js 16 dashboard, React 19, Tailwind CSS 4, Radix UI, Zustand |

Use the Task tool to delegate work to the appropriate agent for complex, multi-step tasks.

## Active Skills (loaded per session)
- **python-patterns**: Python 3.12 idioms, type hints, PEP 8, data classes
- **python-testing**: pytest, TDD, fixtures, mocking, coverage
- **frontend-patterns**: React, Next.js, hooks, state, performance, animations
- **frontend-design**: intentional visual systems, typography, motion
- **backend-patterns**: service layers, repositories, caching, error handling
- **api-design**: REST conventions, pagination, filtering, error responses
- **e2e-testing**: Playwright patterns, POM, CI integration
- **docker-patterns**: multi-stage builds, compose, security
- **coding-standards**: naming, immutability, readability, KISS/DRY/YAGNI
- **security-review**: secrets, input validation, SQL injection, XSS, CSRF, rate limiting
- **tdd-workflow**: red-green-refactor, 80%+ coverage, git checkpoints
- **verification-loop**: build → types → lint → tests → security → diff review
- **strategic-compact**: context management at logical boundaries
- **karpathy-guidelines**: think before coding, simplicity, surgical changes, goal-driven
- **web-design-guidelines**: accessibility, semantic HTML, interaction patterns

## Build, Test, and Development Commands
- `bash scripts/setup_local.sh`: bootstrap local development (creates `venv`, installs deps, seeds `config.json`, runs preflight).
- `source venv/bin/activate && pip install -r requirements.txt`: manual dependency install/update.
- `python3 scripts/preflight_local.py`: validate local provider/config readiness before running tasks.
- `python3 src/main.py`: start the CLI app.
- `bash scripts/upload_video.sh`: run direct script-based upload flow from repo root.
- `python -m pytest tests/ --cov=src --cov-report=term-missing`: run Python tests with coverage.

## Frontend Commands (studio/)
- `cd studio && npm run dev`: start Next.js dev server
- `cd studio && npm run build`: production build
- `cd studio && npm run lint`: ESLint check

## Coding Style & Naming Conventions
- Target Python 3.12 (project requirement in `README.md`).
- Use 4-space indentation and follow existing Python conventions:
  - `snake_case` for functions/variables
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants
- Keep new business logic in focused modules under `src/`; keep provider/integration code in `src/classes/`.
- Prefer small, explicit functions and preserve existing CLI-first behavior.
- TypeScript: strict mode, explicit return types on public APIs, `camelCase` for variables/functions, `PascalCase` for React components.
- Use `interface` over `type` for object shapes unless unions/intersections are needed.

## Testing Guidelines
- Minimum 80% coverage on all new code
- Write tests BEFORE implementation (TDD red-green-refactor)
- Python: pytest with fixtures in `tests/conftest.py`
- Frontend: Vitest for unit tests, Playwright for E2E
- Place tests in a top-level `tests/` directory with names like `test_<module>.py`
- Run `python3 scripts/preflight_local.py` as a smoke test after changes
- Smoke-test impacted flows via `python3 src/main.py`

## Commit & Pull Request Guidelines
- Follow the existing commit style: imperative summaries like `Fix ...`, `Update ...`, optionally with issue refs (for example `(#128)`).
- Open PRs against `main`.
- Link each PR to an issue, keep scope to one feature/fix, and use a clear title + description.
- Mark not-ready PRs with `WIP` and remove it when ready for review.
- Create git checkpoints at each TDD stage (RED → GREEN → REFACTOR).

## Pre-Commit Verification Checklist
Before committing, ensure:
- [ ] `python scripts/preflight_local.py` passes
- [ ] All tests pass with 80%+ coverage
- [ ] No hardcoded API keys or secrets in new code
- [ ] No `console.log` statements in production frontend code
- [ ] TypeScript compiles without errors
- [ ] Git diff reviewed for unintended changes

## Security & Configuration Tips
- Treat `config.json` as environment-specific; do not commit real API keys or private profile paths.
- Start from `config.example.json` and prefer environment variables where supported (for example `GEMINI_API_KEY`).
- Never log API keys, tokens, or SMTP passwords.
- Selenium Firefox profiles contain session cookies — never commit them.
