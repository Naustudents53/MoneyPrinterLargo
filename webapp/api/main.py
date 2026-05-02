"""
MoneyPrinter Pro — FastAPI backend.

Wraps the existing MoneyPrinterV2 Python CLI (src/) into a REST API + SSE
streaming endpoints so the React frontend can drive every workflow:
channels CRUD, video listing/deletion, generation + upload with live logs,
series, settings, system status.

Run from project root:
    python -m uvicorn webapp.api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Paths / sys.path bootstrap
# ---------------------------------------------------------------------------

API_DIR = Path(__file__).resolve().parent
ROOT_DIR = API_DIR.parent.parent
SRC_DIR = ROOT_DIR / "src"
MP_DIR = ROOT_DIR / ".mp"
THUMB_DIR = ROOT_DIR / "thumbnails"
CONFIG_PATH = ROOT_DIR / "config.json"

# Make MoneyPrinterV2 importable. The original config.py computes ROOT_DIR as
# os.path.dirname(sys.path[0]) which only works when invoked as `python src/main.py`
# from the project root. To survive any invocation (uvicorn reload, tests, etc.)
# we (a) add src/ to sys.path and (b) overwrite config.ROOT_DIR after import.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config as mp_config  # noqa: E402

# Force ROOT_DIR to the real project root regardless of how Python was launched.
mp_config.ROOT_DIR = str(ROOT_DIR)
from cache import (  # noqa: E402
    add_account,
    add_product,
    get_accounts,
    get_products,
    get_youtube_cache_path,
    get_twitter_cache_path,
    remove_account,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MoneyPrinter Pro API",
    description="REST + SSE API exposing MoneyPrinterV2 functionality",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class YouTubeChannelIn(BaseModel):
    nickname: str
    firefox_profile: str = ""
    niche: str = ""
    language: str = "español"
    image_style: str = ""
    short_voice: str = ""
    long_voice: str = ""
    hook_profile: str = ""
    voice_drama: bool = False


class YouTubeChannelOut(YouTubeChannelIn):
    id: str
    videos_count: int = 0


class TwitterAccountIn(BaseModel):
    nickname: str
    firefox_profile: str = ""
    topic: str = ""


class TwitterAccountOut(TwitterAccountIn):
    id: str
    posts_count: int = 0


class GenerationRequest(BaseModel):
    custom_topic: str = ""
    image_mode: str = "ai"           # "ai" or "photos"
    kind: str = "short"              # "short" or "long"
    auto_upload: bool = False
    series_id: str = ""              # only used for kind="long"


class ConfigPatch(BaseModel):
    data: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_youtube_raw() -> dict:
    path = get_youtube_cache_path()
    if not os.path.exists(path):
        return {"accounts": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {"accounts": []}


def _write_youtube_raw(data: dict) -> None:
    path = get_youtube_cache_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _read_twitter_raw() -> dict:
    path = get_twitter_cache_path()
    if not os.path.exists(path):
        return {"accounts": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {"accounts": []}


def _write_twitter_raw(data: dict) -> None:
    path = get_twitter_cache_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _channel_out(acc: dict) -> dict:
    return {
        "id": acc.get("id", ""),
        "nickname": acc.get("nickname", ""),
        "firefox_profile": acc.get("firefox_profile", ""),
        "niche": acc.get("niche", ""),
        "language": acc.get("language", "español"),
        "image_style": acc.get("image_style", ""),
        "short_voice": acc.get("short_voice", ""),
        "long_voice": acc.get("long_voice", ""),
        "hook_profile": acc.get("hook_profile", ""),
        "voice_drama": acc.get("voice_drama", False),
        "videos_count": len(acc.get("videos", []) or []),
    }


def _twitter_out(acc: dict) -> dict:
    return {
        "id": acc.get("id", ""),
        "nickname": acc.get("nickname", ""),
        "firefox_profile": acc.get("firefox_profile", ""),
        "topic": acc.get("topic", ""),
        "posts_count": len(acc.get("posts", []) or []),
    }


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@app.get("/api/system/info")
def system_info():
    cfg = _read_config()
    return {
        "root_dir": str(ROOT_DIR),
        "mp_dir_exists": MP_DIR.exists(),
        "config_exists": CONFIG_PATH.exists(),
        "llm_provider": cfg.get("llm_provider", "ollama"),
        "tts_voice": cfg.get("tts_voice", "Jasper"),
        "image_aspect_ratio": cfg.get("nanobanana2_aspect_ratio", "9:16"),
        "stt_provider": cfg.get("stt_provider", "local_whisper"),
        "headless": cfg.get("headless", False),
        "version": "1.0.0",
        "ts": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/system/stats")
def system_stats():
    yt = _read_youtube_raw()
    tw = _read_twitter_raw()
    products = get_products()

    yt_channels = yt.get("accounts", [])
    tw_accounts = tw.get("accounts", [])

    total_videos = sum(len(a.get("videos") or []) for a in yt_channels)
    total_posts = sum(len(a.get("posts") or []) for a in tw_accounts)

    # mp4 disk usage
    mp4_bytes = 0
    mp4_count = 0
    if MP_DIR.exists():
        for p in MP_DIR.iterdir():
            if p.suffix.lower() == ".mp4":
                try:
                    mp4_bytes += p.stat().st_size
                    mp4_count += 1
                except OSError:
                    pass

    # Recent videos across all channels
    recent: list[dict] = []
    for ch in yt_channels:
        for v in ch.get("videos", []) or []:
            recent.append({
                "channel_id": ch.get("id"),
                "channel_nickname": ch.get("nickname"),
                "title": v.get("title", ""),
                "url": v.get("url", ""),
                "date": v.get("date", ""),
            })
    recent.sort(key=lambda x: x["date"] or "", reverse=True)
    recent = recent[:8]

    return {
        "channels_count": len(yt_channels),
        "twitter_accounts_count": len(tw_accounts),
        "products_count": len(products),
        "total_videos": total_videos,
        "total_posts": total_posts,
        "mp4_count": mp4_count,
        "mp4_bytes": mp4_bytes,
        "mp4_mb": round(mp4_bytes / (1024 * 1024), 1),
        "recent_videos": recent,
    }


# ---------------------------------------------------------------------------
# YouTube channels
# ---------------------------------------------------------------------------

@app.get("/api/channels")
def list_channels():
    accounts = get_accounts("youtube")
    return [_channel_out(a) for a in accounts]


@app.get("/api/channels/{channel_id}")
def get_channel(channel_id: str):
    for a in get_accounts("youtube"):
        if a.get("id") == channel_id:
            return _channel_out(a)
    raise HTTPException(404, "Channel not found")


@app.post("/api/channels", status_code=201)
def create_channel(payload: YouTubeChannelIn):
    new_id = str(uuid.uuid4())
    record = {"id": new_id, **payload.model_dump(), "videos": []}
    add_account("youtube", record)
    return _channel_out(record)


@app.put("/api/channels/{channel_id}")
def update_channel(channel_id: str, payload: YouTubeChannelIn):
    raw = _read_youtube_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") == channel_id:
            acc.update(payload.model_dump())
            _write_youtube_raw(raw)
            return _channel_out(acc)
    raise HTTPException(404, "Channel not found")


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str):
    if not any(a.get("id") == channel_id for a in get_accounts("youtube")):
        raise HTTPException(404, "Channel not found")
    remove_account("youtube", channel_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Channel videos
# ---------------------------------------------------------------------------

@app.get("/api/channels/{channel_id}/videos")
def list_channel_videos(channel_id: str):
    raw = _read_youtube_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") == channel_id:
            videos = acc.get("videos", []) or []
            # Most recent first
            sorted_videos = sorted(videos, key=lambda v: v.get("date", ""), reverse=True)
            return [
                {
                    "index": i,
                    "title": v.get("title", ""),
                    "description": v.get("description", ""),
                    "subject": v.get("subject", ""),
                    "url": v.get("url", ""),
                    "date": v.get("date", ""),
                    "is_short": v.get("is_short", True),
                }
                for i, v in enumerate(sorted_videos)
            ]
    raise HTTPException(404, "Channel not found")


@app.delete("/api/channels/{channel_id}/videos")
def delete_channel_video(channel_id: str, url: Optional[str] = None, date: Optional[str] = None):
    """Delete a video from the channel's history (by url + date — both must match)."""
    if not url and not date:
        raise HTTPException(400, "Provide url and/or date to identify the video")
    raw = _read_youtube_raw()
    found = False
    for acc in raw.get("accounts", []):
        if acc.get("id") != channel_id:
            continue
        new_videos = []
        for v in acc.get("videos", []) or []:
            if (url and v.get("url") == url) and (not date or v.get("date") == date):
                found = True
                continue
            if (not url) and date and v.get("date") == date:
                found = True
                continue
            new_videos.append(v)
        acc["videos"] = new_videos
        if found:
            _write_youtube_raw(raw)
            return {"ok": True}
    if not found:
        raise HTTPException(404, "Video not found")
    return {"ok": True}


@app.post("/api/channels/{channel_id}/videos/clear")
def clear_channel_videos(channel_id: str):
    raw = _read_youtube_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") == channel_id:
            acc["videos"] = []
            _write_youtube_raw(raw)
            return {"ok": True, "cleared": True}
    raise HTTPException(404, "Channel not found")


# ---------------------------------------------------------------------------
# Twitter accounts
# ---------------------------------------------------------------------------

@app.get("/api/twitter/accounts")
def list_twitter_accounts():
    return [_twitter_out(a) for a in get_accounts("twitter")]


@app.post("/api/twitter/accounts", status_code=201)
def create_twitter_account(payload: TwitterAccountIn):
    new_id = str(uuid.uuid4())
    record = {"id": new_id, **payload.model_dump(), "posts": []}
    add_account("twitter", record)
    return _twitter_out(record)


@app.put("/api/twitter/accounts/{account_id}")
def update_twitter_account(account_id: str, payload: TwitterAccountIn):
    raw = _read_twitter_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") == account_id:
            acc.update(payload.model_dump())
            _write_twitter_raw(raw)
            return _twitter_out(acc)
    raise HTTPException(404, "Account not found")


@app.delete("/api/twitter/accounts/{account_id}")
def delete_twitter_account(account_id: str):
    if not any(a.get("id") == account_id for a in get_accounts("twitter")):
        raise HTTPException(404, "Account not found")
    remove_account("twitter", account_id)
    return {"ok": True}


@app.get("/api/twitter/accounts/{account_id}/posts")
def list_twitter_posts(account_id: str):
    raw = _read_twitter_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") == account_id:
            posts = acc.get("posts", []) or []
            sorted_posts = sorted(posts, key=lambda p: p.get("date", ""), reverse=True)
            return [
                {
                    "index": i,
                    "content": p.get("content", ""),
                    "date": p.get("date", ""),
                }
                for i, p in enumerate(sorted_posts)
            ]
    raise HTTPException(404, "Account not found")


# ---------------------------------------------------------------------------
# Affiliate Marketing
# ---------------------------------------------------------------------------

@app.get("/api/products")
def list_products():
    return get_products()


@app.post("/api/products", status_code=201)
def create_product(affiliate_link: str, twitter_uuid: str):
    new_id = str(uuid.uuid4())
    record = {"id": new_id, "affiliate_link": affiliate_link, "twitter_uuid": twitter_uuid}
    add_product(record)
    return record


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------

@app.get("/api/series")
def list_series():
    return mp_config.get_series()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Surfaced keys with safe defaults — keep the editor focused on what the user
# realistically tunes (no need to expose 60+ getters).
_CONFIG_FIELD_DEFS = [
    # Core
    {"key": "verbose", "label": "Verbose logs", "type": "bool", "group": "Core"},
    {"key": "headless", "label": "Run browser headless", "type": "bool", "group": "Core"},
    {"key": "threads", "label": "MoviePy threads", "type": "int", "group": "Core"},
    {"key": "is_for_kids", "label": "Mark videos as 'for kids'", "type": "bool", "group": "Core"},
    {"key": "firefox_profile", "label": "Default Firefox profile path", "type": "str", "group": "Core"},
    {"key": "imagemagick_path", "label": "ImageMagick path", "type": "str", "group": "Core"},
    {"key": "font", "label": "Subtitle font filename", "type": "str", "group": "Core"},
    {"key": "script_sentence_length", "label": "Script sentence length", "type": "int", "group": "Core"},
    # LLM
    {"key": "llm_provider", "label": "LLM provider (ollama / pollinations / gemini)", "type": "str", "group": "LLM"},
    {"key": "ollama_base_url", "label": "Ollama base URL", "type": "str", "group": "LLM"},
    {"key": "ollama_model", "label": "Ollama model", "type": "str", "group": "LLM"},
    {"key": "pollinations_text_model", "label": "Pollinations text model", "type": "str", "group": "LLM"},
    # Image
    {"key": "nanobanana2_api_base_url", "label": "Nano Banana 2 base URL", "type": "str", "group": "Image"},
    {"key": "nanobanana2_api_key", "label": "Nano Banana 2 API key", "type": "secret", "group": "Image"},
    {"key": "nanobanana2_model", "label": "Nano Banana 2 model", "type": "str", "group": "Image"},
    {"key": "nanobanana2_aspect_ratio", "label": "Image aspect ratio", "type": "str", "group": "Image"},
    {"key": "pexels_api_key", "label": "Pexels API key", "type": "secret", "group": "Image"},
    {"key": "pixabay_api_key", "label": "Pixabay API key", "type": "secret", "group": "Image"},
    {"key": "europeana_api_key", "label": "Europeana API key", "type": "secret", "group": "Image"},
    {"key": "ideogram_api_key", "label": "Ideogram API key", "type": "secret", "group": "Image"},
    {"key": "leonardo_api_key", "label": "Leonardo API key", "type": "secret", "group": "Image"},
    {"key": "hf_api_key", "label": "HuggingFace API key", "type": "secret", "group": "Image"},
    # TTS / STT
    {"key": "tts_voice", "label": "Default TTS voice", "type": "str", "group": "Audio"},
    {"key": "tts_provider", "label": "TTS provider (edge_tts / kittentts)", "type": "str", "group": "Audio"},
    {"key": "stt_provider", "label": "STT provider", "type": "str", "group": "Audio"},
    {"key": "whisper_model", "label": "Whisper model (base/small/medium/large)", "type": "str", "group": "Audio"},
    {"key": "whisper_device", "label": "Whisper device (auto/cpu/cuda)", "type": "str", "group": "Audio"},
    {"key": "whisper_compute_type", "label": "Whisper compute type", "type": "str", "group": "Audio"},
    {"key": "assembly_ai_api_key", "label": "AssemblyAI API key", "type": "secret", "group": "Audio"},
    # Twitter
    {"key": "twitter_language", "label": "Twitter language", "type": "str", "group": "Twitter"},
]


@app.get("/api/config")
def read_config():
    cfg = _read_config()
    return {"raw": cfg, "fields": _CONFIG_FIELD_DEFS}


@app.put("/api/config")
def update_config(payload: ConfigPatch):
    current = _read_config()
    current.update(payload.data)
    _write_config(current)
    return {"ok": True, "raw": current}


# ---------------------------------------------------------------------------
# Generation / upload — SSE streaming via subprocess
# ---------------------------------------------------------------------------

# Each generation is a long-running subprocess. We expose an SSE endpoint that
# spawns the subprocess and streams stdout line-by-line as `log` events. When
# the process ends, we emit a `done` or `error` event.
#
# To keep the existing CLI logic untouched, we shell out to a small driver
# script (`webapp/api/run_job.py`) that imports the real classes and runs the
# requested step. We could call them in-process, but subprocess isolation
# means a crashing render (Selenium, MoviePy, ffmpeg) doesn't take down the
# API server.

_JOB_RUNNER = API_DIR / "run_job.py"

# Job registry — keeps state for active and recently-finished jobs so UI can
# reattach (re-stream logs, see status) after the user closes the dialog.
_MAX_JOB_LINES = 5000
_FINISHED_TTL = 600  # keep finished jobs queryable for 10 minutes


class JobState:
    __slots__ = (
        "id", "title", "proc", "started_at", "finished_at", "status", "rc",
        "lines", "lock",
    )

    def __init__(self, job_id: str, title: str, proc: subprocess.Popen):
        self.id = job_id
        self.title = title
        self.proc = proc
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.status: str = "running"  # "running" | "done" | "error"
        self.rc: Optional[int] = None
        self.lines: list[str] = []
        # Plain lock — SSE consumers poll the buffer rather than wait on a
        # condition. Polling keeps the asyncio loop unblocked: no executor
        # thread is held idle, so /api/health and other endpoints stay
        # responsive while a job streams.
        self.lock = threading.Lock()

    @property
    def elapsed(self) -> float:
        end = self.finished_at if self.finished_at else time.time()
        return round(end - self.started_at, 1)

    def append(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > _MAX_JOB_LINES:
                drop = len(self.lines) - int(_MAX_JOB_LINES * 0.8)
                self.lines = self.lines[drop:]

    def finish(self, rc: int) -> None:
        with self.lock:
            self.rc = rc
            self.status = "done" if rc == 0 else "error"
            self.finished_at = time.time()

    def snapshot(self, since: int):
        with self.lock:
            new_lines = self.lines[since:]
            return new_lines, len(self.lines), self.status, self.rc


_JOBS: dict[str, JobState] = {}
# RLock so methods that already hold the lock can call helpers that take it
# again. With a plain Lock, _spawn_job (which holds _JOBS_LOCK) calling
# _gc_finished_jobs (which takes it again) produced a deadlock — the thread
# waited on itself, the worker process became unresponsive, and every
# subsequent request that touched _JOBS_LOCK also hung.
_JOBS_LOCK = threading.RLock()


def _gc_finished_jobs_locked() -> None:
    """Drop jobs that finished more than _FINISHED_TTL seconds ago.
    Caller must hold _JOBS_LOCK."""
    cutoff = time.time() - _FINISHED_TTL
    for jid in list(_JOBS.keys()):
        j = _JOBS[jid]
        if j.finished_at and j.finished_at < cutoff:
            _JOBS.pop(jid, None)


def _spawn_job(args: list[str], title: str = "") -> JobState:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [sys.executable, str(_JOB_RUNNER), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT_DIR),
        env=env,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    job_id = uuid.uuid4().hex[:12]
    job = JobState(job_id, title or args[0], proc)
    with _JOBS_LOCK:
        _gc_finished_jobs_locked()
        _JOBS[job_id] = job

    def reader():
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                job.append(line.rstrip("\n"))
        finally:
            rc = proc.wait()
            job.finish(rc)

    threading.Thread(target=reader, daemon=True).start()
    return job


async def _stream_job(job: JobState) -> AsyncIterator[dict]:
    """SSE generator that replays buffered log lines and tails new ones until
    the job reaches a terminal state. Safe for multiple concurrent subscribers.

    Uses asyncio polling rather than executor-bound condition waits so the
    loop stays responsive — no thread is held idle per consumer.
    """
    yield {"event": "start", "data": json.dumps({
        "pid": job.proc.pid, "job_id": job.id, "title": job.title, "ts": job.started_at,
    })}

    sent = 0
    while True:
        new_lines, total, status, rc = job.snapshot(sent)
        for line in new_lines:
            yield {"event": "log", "data": json.dumps({
                "line": line, "elapsed": job.elapsed,
            })}
        sent = total
        if status != "running":
            payload = json.dumps({"rc": rc or 0, "elapsed": job.elapsed})
            yield {"event": "done" if status == "done" else "error", "data": payload}
            return
        # Idle poll. 250ms is fast enough for a live tail and slow enough to
        # be cheap. The job's reader thread fills the buffer continuously
        # whether anyone is listening or not.
        await asyncio.sleep(0.25)


def _job_summary(j: JobState) -> dict:
    last_line = j.lines[-1] if j.lines else ""
    return {
        "id": j.id,
        "title": j.title,
        "status": j.status,
        "started_at": datetime.fromtimestamp(j.started_at).isoformat(),
        "finished_at": datetime.fromtimestamp(j.finished_at).isoformat() if j.finished_at else None,
        "elapsed": j.elapsed,
        "rc": j.rc,
        "last_line": last_line,
        "log_lines": len(j.lines),
    }


@app.get("/api/jobs")
def list_jobs(include_finished: bool = True):
    with _JOBS_LOCK:
        _gc_finished_jobs_locked()
        jobs = list(_JOBS.values())
    if not include_finished:
        jobs = [j for j in jobs if j.status == "running"]
    jobs.sort(key=lambda j: j.started_at, reverse=True)
    return [_job_summary(j) for j in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return _job_summary(j)


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_endpoint(job_id: str):
    """Re-attach to a running or recently-finished job. Replays logs from start."""
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return EventSourceResponse(_stream_job(j))


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found or already finished")
    proc = j.proc
    if proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
        def _ensure_killed():
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        threading.Thread(target=_ensure_killed, daemon=True).start()
    return {"ok": True}


@app.get("/api/channels/{channel_id}/generate")
async def generate_video(
    channel_id: str,
    kind: str = "short",
    custom_topic: str = "",
    image_mode: str = "ai",
    auto_upload: bool = False,
    series_id: str = "",
):
    ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
    if not ch:
        raise HTTPException(404, "Channel not found")
    if kind not in ("short", "long"):
        raise HTTPException(400, "kind must be 'short' or 'long'")

    args = [
        "generate",
        "--channel-id", channel_id,
        "--kind", kind,
        "--image-mode", image_mode,
    ]
    if custom_topic:
        args += ["--topic", custom_topic]
    if auto_upload:
        args += ["--upload"]
    if series_id:
        args += ["--series-id", series_id]

    label = "Short" if kind == "short" else "Long video"
    title = f"Generando {label} — {ch.get('nickname', channel_id)}"
    job = _spawn_job(args, title=title)
    return EventSourceResponse(_stream_job(job))


@app.get("/api/channels/{channel_id}/upload-last")
async def upload_last(channel_id: str, kind: str = "short"):
    """Upload the most recently generated video for this channel (post-generation)."""
    ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
    if not ch:
        raise HTTPException(404, "Channel not found")
    if kind not in ("short", "long"):
        raise HTTPException(400, "kind must be 'short' or 'long'")
    title = f"Subiendo {kind} — {ch.get('nickname', channel_id)}"
    job = _spawn_job(["upload-last", "--channel-id", channel_id, "--kind", kind], title=title)
    return EventSourceResponse(_stream_job(job))


@app.get("/api/twitter/accounts/{account_id}/post")
async def post_tweet(account_id: str):
    acc = next((a for a in get_accounts("twitter") if a.get("id") == account_id), None)
    if not acc:
        raise HTTPException(404, "Account not found")
    title = f"Posteando tweet — {acc.get('nickname', account_id)}"
    job = _spawn_job(["tweet", "--account-id", account_id], title=title)
    return EventSourceResponse(_stream_job(job))


# ---------------------------------------------------------------------------
# .mp file management
# ---------------------------------------------------------------------------

@app.get("/api/storage/mp4")
def list_mp4():
    if not MP_DIR.exists():
        return []
    out = []
    for p in MP_DIR.iterdir():
        if p.suffix.lower() == ".mp4":
            try:
                stat = p.stat()
                out.append({
                    "name": p.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 1),
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                pass
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


@app.get("/api/storage/mp4/{filename}/raw")
def stream_mp4(filename: str):
    target = MP_DIR / filename
    if target.parent != MP_DIR or not target.exists():
        raise HTTPException(404, "File not found")
    if target.suffix.lower() != ".mp4":
        raise HTTPException(400, "Only .mp4 files allowed")
    return FileResponse(str(target), media_type="video/mp4", filename=filename)


@app.delete("/api/storage/mp4/{filename}")
def delete_mp4(filename: str):
    # Prevent path traversal — only accept names that exist verbatim in MP_DIR
    target = MP_DIR / filename
    if target.parent != MP_DIR or not target.exists():
        raise HTTPException(404, "File not found")
    if target.suffix.lower() != ".mp4":
        raise HTTPException(400, "Only .mp4 files allowed")
    target.unlink()
    return {"ok": True}


@app.post("/api/storage/mp4/clear")
def clear_mp4():
    if not MP_DIR.exists():
        return {"ok": True, "deleted": 0}
    deleted = 0
    for p in MP_DIR.iterdir():
        if p.suffix.lower() == ".mp4":
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
    return {"ok": True, "deleted": deleted}


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------

class ThumbnailRequest(BaseModel):
    topic: str
    text: str
    visual: str = ""


def _safe_thumb_path(filename: str) -> Path:
    """Resolve filename inside THUMB_DIR, refusing path traversal."""
    target = (THUMB_DIR / filename).resolve()
    if THUMB_DIR.resolve() not in target.parents and target != THUMB_DIR.resolve():
        raise HTTPException(400, "Invalid filename")
    if target.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Only image files allowed")
    return target


@app.get("/api/thumbnails")
def list_thumbnails():
    if not THUMB_DIR.exists():
        return []
    out = []
    for p in THUMB_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                stat = p.stat()
                out.append({
                    "name": p.name,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except OSError:
                pass
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


@app.get("/api/thumbnails/{filename}/raw")
def get_thumbnail_raw(filename: str):
    target = _safe_thumb_path(filename)
    if not target.exists():
        raise HTTPException(404, "Thumbnail not found")
    media = "image/png" if target.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(target), media_type=media, filename=filename)


@app.delete("/api/thumbnails/{filename}")
def delete_thumbnail(filename: str):
    target = _safe_thumb_path(filename)
    if not target.exists():
        raise HTTPException(404, "Thumbnail not found")
    target.unlink()
    return {"ok": True}


@app.post("/api/thumbnails/clear")
def clear_thumbnails():
    if not THUMB_DIR.exists():
        return {"ok": True, "deleted": 0}
    deleted = 0
    for p in THUMB_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
    return {"ok": True, "deleted": deleted}


@app.get("/api/thumbnails/generate")
async def generate_thumbnail(topic: str, text: str, visual: str = ""):
    """Run scripts/make_thumbnail.py as a streaming subprocess. Output goes to thumbnails/."""
    if not topic.strip() or not text.strip():
        raise HTTPException(400, "topic and text are required")
    THUMB_DIR.mkdir(exist_ok=True)
    out_name = f"thumb_{uuid.uuid4()}.png"
    out_path = THUMB_DIR / out_name
    args = ["thumbnail", "--topic", topic, "--text", text, "--out", str(out_path)]
    if visual.strip():
        args += ["--visual", visual]
    job = _spawn_job(args, title=f"Thumbnail — {text[:40]}")
    return EventSourceResponse(_stream_job(job))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat() + "Z"}


# Allow `python webapp/api/main.py` for convenience
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.api.main:app", host="127.0.0.1", port=8000, reload=False)
