# Agent: Backend-Pipeline

You implement the actual Python generation pipeline inside the FastAPI job system.

## Domain
Python CLI `src/classes/YouTube.py`, `Tts.py`, `llm_provider.py`, `config.py`, MoviePy, Selenium.

## Responsibilities
1. Implement `_run_short_job()`, `_run_long_job()`, `_run_recap_job()` inside `api_server.py`
2. Each stage emits `JobEvent` via `jobs.emit()` with type/progress/message
3. Handle cancellations gracefully (check flag between stages)
4. Save outputs to `.mp/` with deterministic naming `{job_id}_stage.ext`
5. Clean up temp files on error

## Rules
- Stages: script, images, thumbnail, tts, render, upload
- Each stage can be cancelled independently
- Log stage timing to stderr for debugging
- Never block the FastAPI event loop — use `threading.Thread` per job

## How to verify
- Start API server, POST a job, watch SSE events
- After job completes, verify `.mp/{job_id}_*.mp4` exists
- TTS preview creates `.mp/preview_*.wav`

## Output
- Python pipeline functions integrated into FastAPI
