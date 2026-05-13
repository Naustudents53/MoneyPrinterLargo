"""
MoneyPrinter Largo — FastAPI backend.

Wraps the existing MoneyPrinterLargo Python CLI (src/) into a REST API + SSE
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
import re
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
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

# Make MoneyPrinterLargo importable. The original config.py computes ROOT_DIR as
# os.path.dirname(sys.path[0]) which only works when invoked as `python src/main.py`
# from the project root. To survive any invocation (uvicorn reload, tests, etc.)
# we (a) add src/ to sys.path and (b) overwrite config.ROOT_DIR after import.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
# Also add API_DIR so sibling modules (auto_sync, run_job) can be imported by
# bare name regardless of whether uvicorn loaded us as `webapp.api.main` or
# directly as `main`. Without this, the lifespan handler's lazy import of
# auto_sync fails with ModuleNotFoundError on uvicorn startup.
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

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

# Operations / observability router (disk, cost, errors, logs, webhooks, backup).
# Try the package-relative import first (uvicorn invokes us as webapp.api.main);
# fall back to a sibling import if someone runs main.py directly.
try:
    from . import ops  # noqa: E402
except ImportError:
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    import ops  # type: ignore  # noqa: E402
ops.init(ROOT_DIR, MP_DIR, CONFIG_PATH)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

# Auto-sync scheduler: started on app startup, stopped on shutdown. We keep
# the instance module-level so the /api/auto-sync/* endpoints can reach it.
_auto_sync_scheduler = None  # populated in lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _auto_sync_scheduler
    from auto_sync import AutoSyncScheduler  # lazy: keeps test imports light

    _auto_sync_scheduler = AutoSyncScheduler(
        root_dir=ROOT_DIR,
        config_loader=_read_config,
    )
    try:
        _auto_sync_scheduler.start()
    except Exception as e:
        print(f"[main] WARN: could not start auto-sync scheduler: {e}", flush=True)
    try:
        yield
    finally:
        if _auto_sync_scheduler is not None:
            try:
                await _auto_sync_scheduler.stop()
            except Exception as e:
                print(f"[main] WARN: scheduler shutdown failed: {e}", flush=True)


app = FastAPI(
    title="MoneyPrinter Largo API",
    description="REST + SSE API exposing MoneyPrinterLargo functionality",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ops.router)


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
    # Public channel handle or full URL (e.g. "@andrecronicas" or
    # "https://www.youtube.com/@andrecronicas"). Used by the cache-sync
    # script to fetch the actual list of uploaded videos / shorts.
    youtube_handle: str = ""


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
        "youtube_handle": acc.get("youtube_handle", ""),
        "videos_count": len(acc.get("videos", []) or []),
        # Populated by scripts/sync_youtube_cache.py. `null` means the channel
        # has never been synced; the frontend renders that as a muted "—".
        "subscriber_count": acc.get("subscriber_count"),
        "stats_synced_at": acc.get("stats_synced_at", ""),
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


def _infer_llm_provider_from_model(model_id: str) -> str:
    m = (model_id or "").strip().lower()
    if not m:
        return ""
    if m.startswith("gemini-") or m.startswith("gemma-"):
        return "gemini"
    if m.startswith("gpt-") or m.startswith("chatgpt-") or m.startswith(("o1", "o3", "o4")):
        return "openai"
    if ":" in m:
        return "ollama"
    return "pollinations"


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
        "image_aspect_ratio": "9:16",
        "short_render_profile": cfg.get("short_render_profile", "quality"),
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

def _infer_is_short(v: dict) -> bool:
    """Best-effort detection for legacy cache entries that don't have an
    explicit `is_short` field. Going forward `is_short` is always written by
    `YouTube.upload_video`, so this only kicks in for old records.

    Heuristics:
      - explicit `is_short` value wins
      - presence of a #Shorts hashtag (case-insensitive) → short
      - everything else → long (false). Default-to-short is wrong because in
        this project most legacy uploads are long-form.
    """
    if "is_short" in v:
        return bool(v["is_short"])
    text = ((v.get("title") or "") + " " + (v.get("description") or "")).lower()
    if "#short" in text or "#shorts" in text:
        return True
    return False


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
                    "is_short": _infer_is_short(v),
                    # Engagement stats are populated by scripts/sync_youtube_cache.py.
                    # Missing (= never synced) is reported as -1 so the UI can
                    # show "—" instead of a misleading "0".
                    "view_count": v.get("view_count", -1),
                    "like_count": v.get("like_count", -1),
                    "comment_count": v.get("comment_count", -1),
                    "dislike_count": v.get("dislike_count", -1),
                    "stats_synced_at": v.get("stats_synced_at", ""),
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


class VideoEdit(BaseModel):
    # Identifier — both url and date must match the entry being edited so we
    # don't accidentally update the wrong video when multiple share a title.
    url: str
    date: str
    # Editable fields. Sent as Optional so the frontend can patch a subset.
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    is_short: Optional[bool] = None


@app.patch("/api/channels/{channel_id}/videos")
def edit_channel_video(channel_id: str, payload: VideoEdit):
    """Update title / subject / description / kind of a video entry in the
    channel's history. The video is identified by (url, date) which together
    are unique in practice."""
    raw = _read_youtube_raw()
    for acc in raw.get("accounts", []):
        if acc.get("id") != channel_id:
            continue
        for v in acc.get("videos", []) or []:
            if v.get("url") == payload.url and v.get("date") == payload.date:
                if payload.title is not None:
                    v["title"] = payload.title
                if payload.subject is not None:
                    v["subject"] = payload.subject
                if payload.description is not None:
                    v["description"] = payload.description
                if payload.is_short is not None:
                    v["is_short"] = bool(payload.is_short)
                _write_youtube_raw(raw)
                return {"ok": True, "video": v}
        raise HTTPException(404, "Video not found in this channel")
    raise HTTPException(404, "Channel not found")


@app.post("/api/channels/{channel_id}/videos/mark-all")
def mark_all_videos_kind(channel_id: str, kind: str):
    """Bulk-set is_short on every video entry in the channel.
    `kind` must be 'short' or 'long'. Useful one-shot to fix legacy entries
    where is_short was never recorded."""
    if kind not in ("short", "long"):
        raise HTTPException(400, "kind must be 'short' or 'long'")
    is_short = kind == "short"
    raw = _read_youtube_raw()
    updated = 0
    for acc in raw.get("accounts", []):
        if acc.get("id") != channel_id:
            continue
        for v in acc.get("videos", []) or []:
            if v.get("is_short") != is_short:
                v["is_short"] = is_short
                updated += 1
        _write_youtube_raw(raw)
        return {"ok": True, "updated": updated, "kind": kind}
    raise HTTPException(404, "Channel not found")


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
    {"key": "llm_provider", "label": "LLM provider (openai / gemini / ollama / pollinations)", "type": "str", "group": "LLM"},
    {"key": "openai_api_key", "label": "OpenAI API key", "type": "secret", "group": "LLM"},
    {"key": "openai_base_url", "label": "OpenAI base URL", "type": "str", "group": "LLM"},
    {"key": "openai_model", "label": "OpenAI default model", "type": "str", "group": "LLM"},
    {"key": "openai_reasoning_effort", "label": "OpenAI reasoning effort", "type": "str", "group": "LLM"},
    {"key": "ollama_base_url", "label": "Ollama base URL", "type": "str", "group": "LLM"},
    {"key": "ollama_model", "label": "Ollama model", "type": "str", "group": "LLM"},
    # Image
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


# Curated list of LLM models the user can pick as override for a single
# generation job. We deliberately keep this short and group it by provider so
# the UI dropdown stays readable. The default (used when the user doesn't
# touch the selector) matches the first entry of `gemini_models` in config.json.
_OPENAI_MODEL_CATALOG = [
    {"id": "gpt-5.5", "label": "GPT-5.5", "provider": "openai",
     "description": "OpenAI frontier model para razonamiento, guiones largos y máxima calidad."},
    {"id": "gpt-5.5-2026-04-23", "label": "GPT-5.5 (snapshot 2026-04-23)", "provider": "openai",
     "description": "Snapshot estable de GPT-5.5 para resultados reproducibles."},
    {"id": "gpt-5.4", "label": "GPT-5.4", "provider": "openai",
     "description": "Modelo OpenAI potente con menor coste que GPT-5.5."},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "provider": "openai",
     "description": "Más rápido y económico para volumen alto."},
]

_GEMINI_MODEL_CATALOG = [
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash (preview)", "provider": "gemini",
     "description": "Default — más reciente, mejor balance velocidad/calidad."},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "provider": "gemini",
     "description": "Probado, alta calidad para texto."},
    {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite", "provider": "gemini",
     "description": "Más rápido y barato; 10 RPM free tier."},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite", "provider": "gemini",
     "description": "500 RPD free tier — buen volumen."},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "provider": "gemini",
     "description": "Mayor calidad (requiere billing)."},
    {"id": "gemma-4-31b", "label": "Gemma 4 31B", "provider": "gemini",
     "description": "Open model: 1.5K RPD free tier, TPM ilimitado."},
    {"id": "gemma-4-26b", "label": "Gemma 4 26B", "provider": "gemini",
     "description": "Más ligero: 1.5K RPD free tier."},
]


@app.get("/api/llm/models")
def list_llm_models():
    """Return the catalog of LLM models the UI can offer for per-job model
    selection. Always includes the curated Gemini catalog; appends Ollama
    models if an Ollama server is reachable so the user can route a single
    job to local hardware without touching settings."""
    cfg = _read_config()
    default_model = ""
    active_provider = cfg.get("llm_provider", "gemini")
    if active_provider == "openai":
        openai_models = cfg.get("openai_models") or []
        if openai_models:
            default_model = openai_models[0]
        elif cfg.get("openai_model"):
            default_model = cfg["openai_model"]
    else:
        gem_models = cfg.get("gemini_models") or []
        if gem_models:
            default_model = gem_models[0]
        elif cfg.get("gemini_model"):
            default_model = cfg["gemini_model"]

    out = list(_OPENAI_MODEL_CATALOG) + list(_GEMINI_MODEL_CATALOG)

    # Ollama models — combine: (a) what's actually installed/available on the
    # local Ollama server, (b) a curated catalog of cloud-hosted Ollama models
    # the user may want to try without installing them first. The cloud
    # variants tagged ":cloud" are served by Ollama's hosted inference and
    # don't need a local download, so it's safe to surface them upfront.
    installed: set[str] = set()
    try:
        import importlib
        llm_mod = importlib.import_module("llm_provider")
        original_provider = getattr(llm_mod, "_llm_provider", None)
        llm_mod.set_llm_provider("ollama")
        try:
            installed = set(llm_mod.list_models())
        finally:
            llm_mod.set_llm_provider(original_provider or "")
    except Exception:
        pass

    # Curated Ollama catalog — covers the most-used cloud variants plus the
    # popular local models. Order: cloud first (always available), then locals
    # (only useful if the user has them pulled).
    _OLLAMA_CATALOG = [
        # Cloud-hosted (no local pull needed, billed by Ollama subscription)
        ("kimi-k2.6:cloud",         "Kimi K2.6 (cloud)",         "Moonshot Kimi — fuerte razonamiento y escritura larga."),
        ("glm-5.1:cloud",           "GLM 5.1 (cloud)",           "Zhipu GLM 5.1 — multilingüe, buena prosa."),
        ("qwen3.5:cloud",           "Qwen 3.5 (cloud)",          "Qwen 3.5 — alto rendimiento, multilingüe."),
        ("qwen3.6:cloud",           "Qwen 3.6 (cloud)",          "Más reciente que 3.5, mejor seguimiento de instrucciones."),
        ("nemotron-3-super:cloud",  "Nemotron 3 Super (cloud)",  "NVIDIA Nemotron — texto narrativo de alta calidad."),
        ("gemma4:31b-cloud",        "Gemma 4 31B (cloud)",       "Google Gemma 4 — open weights, gran ventana de contexto."),
        ("llama3.3:70b-cloud",      "Llama 3.3 70B (cloud)",     "Meta Llama 3.3 70B — generalista potente."),
        ("deepseek-v3.1:cloud",     "DeepSeek V3.1 (cloud)",     "DeepSeek V3 — buen ratio calidad/coste."),
        # Local pull-only — useful if the user has Ollama running locally with
        # these models downloaded.
        ("gemma4:latest",           "Gemma 4 (local)",           "Modelo local de Google Gemma 4."),
        ("qwen3.6:latest",          "Qwen 3.6 (local)",          "Modelo local Qwen 3.6."),
        ("llama3.2:latest",         "Llama 3.2 (local)",         "Llama 3.2 local — rápido y ligero."),
        ("llama3.3:latest",         "Llama 3.3 (local)",         "Llama 3.3 local — más capaz que 3.2."),
        ("mistral:latest",          "Mistral 7B (local)",        "Mistral 7B local — eficiente."),
        ("phi3:latest",             "Phi-3 (local)",             "Microsoft Phi-3 — pequeño y rápido."),
        ("codellama:latest",        "CodeLlama (local)",         "Variante orientada a código."),
    ]

    catalog_ids: set[str] = set()
    for mid, label, desc in _OLLAMA_CATALOG:
        catalog_ids.add(mid)
        is_installed = mid in installed
        # Tag the description so the user knows whether the model is ready to
        # run locally or will need to be pulled / require cloud credentials.
        suffix = ""
        if mid.endswith(":cloud"):
            suffix = " [requiere Ollama cloud]"
        elif is_installed:
            suffix = " [instalado ✓]"
        else:
            suffix = " [no instalado — corre `ollama pull` primero]"
        out.append({
            "id": mid,
            "label": label,
            "provider": "ollama",
            "description": desc + suffix,
        })

    # Any installed model NOT in the curated catalog gets appended at the end
    # so the user can still pick it (e.g. a custom fine-tune).
    for m in sorted(installed):
        if m in catalog_ids:
            continue
        out.append({
            "id": m,
            "label": f"{m} (local)",
            "provider": "ollama",
            "description": "Modelo local instalado [✓].",
        })

    # Pollinations — small curated set, used as fallback or override.
    for pid, plabel in [
        ("openai", "Pollinations · OpenAI (gpt-style)"),
        ("openai-large", "Pollinations · OpenAI Large"),
        ("deepseek", "Pollinations · DeepSeek"),
        ("llama", "Pollinations · Llama"),
        ("mistral", "Pollinations · Mistral"),
    ]:
        out.append({
            "id": pid,
            "label": plabel,
            "provider": "pollinations",
            "description": "Modelo gratis vía Pollinations (sin API key).",
        })

    return {
        "models": out,
        "default": default_model or ("gpt-5.5" if active_provider == "openai" else "gemini-3-flash-preview"),
        "active_provider": active_provider,
    }


@app.get("/api/llm/hook-styles")
def list_hook_styles():
    """Return every hook style declared in HOOK_PROFILES, flattened so the UI
    can offer a single dropdown grouped by profile. Each style id encodes the
    profile so a single string round-trips back through the override env var
    without ambiguity."""
    from classes.YouTube import HOOK_PROFILES  # lazy import — keeps startup light

    out = []
    for profile_name, styles in HOOK_PROFILES.items():
        for style_name, example in styles:
            # Truncate the example so the dropdown stays readable — full text
            # lives in the source, the UI just needs a snippet to differentiate.
            snippet = example.strip()
            if len(snippet) > 120:
                snippet = snippet[:117].rstrip() + "…"
            out.append({
                "id": f"{profile_name}::{style_name}",
                "profile": profile_name,
                "name": style_name,
                "example": snippet,
            })
    return {"styles": out}


@app.get("/api/voices")
def list_voices():
    """
    Curated Edge-TTS voices available for channel narration. Returns alias,
    full voice ID and a language tag derived from the voice ID prefix
    (e.g. es-ES → es-ES). The frontend uses this to populate the Voz
    dropdowns in the channel form.
    """
    from classes.Tts import EDGE_TTS_VOICES  # noqa: WPS433 (lazy import — keeps API startup light)

    voices = []
    for alias, voice_id in EDGE_TTS_VOICES.items():
        parts = voice_id.split("-")
        lang_tag = "-".join(parts[:2]) if len(parts) >= 2 else voice_id
        voices.append({
            "alias": alias,
            "voice_id": voice_id,
            "language": lang_tag,
        })
    return {"voices": voices}


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
        "lines", "lock", "channel_id", "kind",
    )

    def __init__(self, job_id: str, title: str, proc: subprocess.Popen,
                 channel_id: Optional[str] = None, kind: Optional[str] = None):
        self.id = job_id
        self.title = title
        self.proc = proc
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.status: str = "running"  # "running" | "done" | "error"
        self.rc: Optional[int] = None
        self.lines: list[str] = []
        # Optional context so the UI can offer "Subir a YouTube" when
        # reattaching to a finished generation job from the background panel.
        # Only set for YouTube generation jobs; upload-last and other jobs
        # leave these None so the upload button doesn't appear in places it
        # shouldn't (e.g. already-uploaded jobs, sync jobs, tweet jobs).
        self.channel_id: Optional[str] = channel_id
        self.kind: Optional[str] = kind
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
        # Persist a summary + full log to disk and fire webhooks. Done outside
        # the lock so a slow webhook can't block log readers.
        try:
            _persist_finished_job(self)
        except Exception as exc:
            print(f"[ops] WARN: failed to persist job {self.id}: {exc}")

    def snapshot(self, since: int):
        with self.lock:
            new_lines = self.lines[since:]
            return new_lines, len(self.lines), self.status, self.rc


def _persist_finished_job(job: "JobState") -> None:
    """Write a one-line summary to .mp/job_log.jsonl, dump the full log to
    .mp/job_logs/<id>.log, and fire the configured webhook. Idempotent — safe
    to call once per job."""
    summary = _job_summary(job)
    # Persist full log so the History page can display it after the in-memory
    # buffer ages out (TTL 10 min).
    log_dir = MP_DIR / "job_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / f"{job.id}.log", "w", encoding="utf-8") as f:
            f.write("\n".join(job.lines))
    except OSError as exc:
        print(f"[ops] WARN: could not write job log file: {exc}")

    record = {
        **summary,
        "ended_ts": job.finished_at,
        "log_path": f"job_logs/{job.id}.log",
    }
    ops.append_job_record(record)
    # Webhooks are best-effort — failures are swallowed inside fire_webhook.
    ops.maybe_notify_job_finished(record)


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


def _spawn_job(args: list[str], title: str = "",
               channel_id: Optional[str] = None,
               kind: Optional[str] = None) -> JobState:
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
    job = JobState(job_id, title or args[0], proc, channel_id=channel_id, kind=kind)
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
        "channel_id": j.channel_id,
        "kind": j.kind,
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


@app.get("/api/llm/models")
def list_llm_models():
    """Return the list of available models per provider so the UI can offer
    a dropdown override per generation. Failures on a single provider are
    swallowed so a missing Ollama daemon doesn't break the whole endpoint.
    """
    out: dict[str, Any] = {"ollama": [], "gemini": [], "pollinations": [], "errors": {}}

    try:
        from llm_provider import list_models as _list_ollama
        out["ollama"] = _list_ollama()
    except Exception as e:
        out["errors"]["ollama"] = str(e)[:200]

    try:
        from config import get_gemini_models, get_gemini_api_key
        if get_gemini_api_key():
            out["gemini"] = list(get_gemini_models() or [])
        else:
            out["errors"]["gemini"] = "no gemini_api_key in config.json"
    except Exception as e:
        out["errors"]["gemini"] = str(e)[:200]

    try:
        from llm_provider import _list_pollinations_models
        out["pollinations"] = _list_pollinations_models()
    except Exception as e:
        out["errors"]["pollinations"] = str(e)[:200]

    return out



# ---------------------------------------------------------------------------
# AI-assisted helpers — topic suggestions + script preview
# ---------------------------------------------------------------------------

@app.get("/api/channels/{channel_id}/suggest-topics")
def suggest_topics(channel_id: str, n: int = 5, model: str = ""):
    """Ask the LLM for `n` topic ideas tailored to the channel's niche and
    language. Returns synchronously (one LLM call, not a streaming job) so
    the UI can pop them inline. Reads the channel's recent subjects from the
    cache and asks the LLM to avoid repeating them."""
    ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
    if not ch:
        raise HTTPException(404, "Channel not found")
    n = max(1, min(int(n or 5), 10))

    # Recent subjects → injected into the prompt so suggestions stay fresh.
    raw = _read_youtube_raw()
    recent_subjects: list[str] = []
    for acc in raw.get("accounts", []):
        if acc.get("id") == channel_id:
            for v in (acc.get("videos") or [])[:30]:
                s = (v.get("subject") or v.get("title") or "").strip()
                if s:
                    recent_subjects.append(s)
            break

    niche = ch.get("niche") or "(sin niche)"
    language = ch.get("language") or "español"
    avoid_block = ""
    if recent_subjects:
        # Cap to ~20 entries to keep the prompt small.
        bullets = "\n".join(f"- {s}" for s in recent_subjects[:20])
        avoid_block = (
            "\n\nTEMAS RECIENTES A EVITAR (no repitas ni reformules estos):\n"
            f"{bullets}\n"
        )

    prompt = (
        f"Eres un experto en creación de contenido para YouTube Shorts. "
        f"Genera EXACTAMENTE {n} ideas de temas concretos para un canal en {language} "
        f"sobre: {niche}.\n\n"
        f"REGLAS ESTRICTAS:\n"
        f"- Cada idea debe ser un TEMA específico (no un concepto abstracto). "
        f"Por ejemplo: 'La caída de Constantinopla en 1453' NO 'la historia bizantina'.\n"
        f"- Cada idea ocupa UNA línea, sin numeración, sin guiones, sin viñetas.\n"
        f"- Cada idea debe ser entendible por sí sola y digna de un short de 30-60s.\n"
        f"- Escribe EN {language}.\n"
        f"- NO incluyas explicaciones, encabezados ni nada extra. Solo las {n} líneas con los temas."
        f"{avoid_block}"
    )

    # Apply per-job model override (same env-var trick used by the runner)
    saved_override = os.environ.get("MP_GEMINI_MODEL_OVERRIDE", "")
    if model and (model.startswith("gemini-") or model.startswith("gemma-")):
        os.environ["MP_GEMINI_MODEL_OVERRIDE"] = model
    try:
        from llm_provider import generate_text  # lazy import — keeps API startup fast
        raw_out = generate_text(prompt, temperature=0.9)
    except Exception as e:
        raise HTTPException(500, f"LLM failure: {e}") from e
    finally:
        if saved_override:
            os.environ["MP_GEMINI_MODEL_OVERRIDE"] = saved_override
        else:
            os.environ.pop("MP_GEMINI_MODEL_OVERRIDE", None)

    # Clean up: drop empty lines, strip bullets/numbering, dedupe.
    import re as _re
    candidates: list[str] = []
    seen: set[str] = set()
    for line in (raw_out or "").splitlines():
        clean = _re.sub(r"^[\s\-\*•\d\.\)]+", "", line).strip()
        if not clean or len(clean) < 6:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(clean)
        if len(candidates) >= n:
            break

    return {"topics": candidates}


# Preview-script artifacts live in .mp/.preview-<uuid>.txt — the same directory
# as the rest of the pipeline scratch space, prefixed so rem_temp_files() won't
# wipe them (they end in .txt which is allowed to stay).
@app.get("/api/channels/{channel_id}/preview-script")
async def preview_script(
    channel_id: str,
    kind: str = "short",
    custom_topic: str = "",
    model: str = "",
    sentence_length: int = 0,
    hook_style: str = "",
):
    """Run only the subject + script generation steps and stream progress as
    SSE. The runner writes the result to a .mp/.preview-<uuid>.txt file; the
    UI then reads the content and (after approval) passes the same uuid back
    to /generate?script_file=<uuid> to skip script generation."""
    ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
    if not ch:
        raise HTTPException(404, "Channel not found")
    if kind not in ("short",):
        raise HTTPException(400, "Preview only supports kind='short' for now")

    args = ["preview-script", "--channel-id", channel_id]
    if custom_topic:
        args += ["--topic", custom_topic]
    if model:
        args += ["--model", model]
    if sentence_length and sentence_length > 0:
        args += ["--sentence-length", str(sentence_length)]
    if hook_style:
        args += ["--hook-style", hook_style]

    title = f"Previa de script — {ch.get('nickname', channel_id)}"
    job = _spawn_job(args, title=title, channel_id=channel_id, kind="short")
    return EventSourceResponse(_stream_job(job))


@app.get("/api/preview/{preview_id}")
def read_preview(preview_id: str):
    """Return the content of a previously-generated preview script. Format:
    {subject, script}. Used by the frontend after the SSE stream finishes."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{4,64}", preview_id):
        raise HTTPException(400, "Invalid preview id")
    path = MP_DIR / f".preview-{preview_id}.txt"
    if not path.is_file():
        raise HTTPException(404, "Preview not found or already consumed")
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Could not read preview: {e}") from e
    head, _, body = raw.partition("\n\n")
    return {"id": preview_id, "subject": (head or "").strip(), "script": (body or "").strip()}


class PreviewSave(BaseModel):
    subject: str
    script: str


@app.put("/api/preview/{preview_id}")
def save_preview(preview_id: str, payload: PreviewSave):
    """Persist an edited preview script back to disk so the subsequent
    /generate call picks up the user's changes. The frontend calls this only
    when the user actually modifies the textarea before clicking 'continuar'."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{4,64}", preview_id):
        raise HTTPException(400, "Invalid preview id")
    path = MP_DIR / f".preview-{preview_id}.txt"
    if not path.is_file():
        raise HTTPException(404, "Preview not found")
    subject = (payload.subject or "").strip()
    script = (payload.script or "").strip()
    if not subject or not script:
        raise HTTPException(400, "subject and script are required")
    try:
        path.write_text(f"{subject}\n\n{script}\n", encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Could not write preview: {e}") from e
    return {"ok": True}


# ---------------------------------------------------------------------------
# Generation endpoints
# ---------------------------------------------------------------------------

@app.get("/api/channels/{channel_id}/generate")
async def generate_video(
    channel_id: str,
    kind: str = "short",
    custom_topic: str = "",
    image_mode: str = "ai",
    auto_upload: bool = False,
    series_id: str = "",
    duration_seconds: int = 0,
    render_profile: str = "",
    llm_provider: str = "",
    llm_model: str = "",
    model: str = "",
    sentence_length: int = 0,
    hook_style: str = "",
    script_file: str = "",
):
    ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
    if not ch:
        raise HTTPException(404, "Channel not found")
    if kind not in ("short", "long"):
        raise HTTPException(400, "kind must be 'short' or 'long'")

    # Validate duration preset early so the user gets a clean 400 instead of
    # waiting for the subprocess to warn and silently fall back.
    if kind == "short" and duration_seconds:
        from classes.duration_presets import ALLOWED_SHORT_DURATIONS
        if duration_seconds not in ALLOWED_SHORT_DURATIONS:
            raise HTTPException(
                400,
                f"duration_seconds must be one of {list(ALLOWED_SHORT_DURATIONS)}",
            )

    if llm_provider and llm_provider not in ("ollama", "gemini"):
        raise HTTPException(400, "llm_provider must be 'ollama' or 'gemini'")

    if kind == "short" and render_profile and render_profile not in ("quality", "fast", "turbo"):
        raise HTTPException(400, "render_profile must be 'quality', 'fast', or 'turbo'")

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
    if kind == "short" and duration_seconds:
        args += ["--duration", str(duration_seconds)]
    if kind == "short" and render_profile:
        args += ["--render-profile", render_profile]
    if llm_provider:
        args += ["--llm-provider", llm_provider]
    if llm_model:
        args += ["--llm-model", llm_model]
    if model:
        args += ["--model", model]
    if sentence_length and sentence_length > 0:
        args += ["--sentence-length", str(sentence_length)]
    if hook_style:
        args += ["--hook-style", hook_style]
    if script_file:
        # Resolve the script ref to a real .mp/ path. The frontend only sees
        # the opaque preview id (a uuid) returned by /preview-script — we
        # translate it to the actual file here so the runner stays simple.
        script_path = MP_DIR / f".preview-{script_file}.txt"
        if not script_path.is_file():
            raise HTTPException(400, f"Preview script {script_file!r} not found")
        args += ["--script-file", str(script_path)]

    label = "Short" if kind == "short" else "Long video"
    title = f"Generando {label} — {ch.get('nickname', channel_id)}"
    job = _spawn_job(args, title=title, channel_id=channel_id, kind=kind)
    return EventSourceResponse(_stream_job(job))


class BatchJobItem(BaseModel):
    channel_id: str
    kind: str = "short"
    custom_topic: str = ""
    image_mode: str = "ai"
    auto_upload: bool = False
    series_id: str = ""
    model: str = ""
    sentence_length: int = 0
    hook_style: str = ""
    render_profile: str = ""


class BatchGeneratePayload(BaseModel):
    jobs: list[BatchJobItem]


@app.post("/api/generate-batch")
def generate_batch(payload: BatchGeneratePayload):
    """Spawn N generation jobs in parallel — one subprocess per item — and
    return the list of created job ids so the UI can subscribe to each
    via /api/jobs/<id>/stream individually.

    Each item is independent: different channels, kinds, topics, even
    models. We don't enforce a hard cap here (the limiting factor is your
    Gemini RPM and disk I/O) but the UI surfaces a guard for sanity."""
    if not payload.jobs:
        raise HTTPException(400, "Empty job list")
    if len(payload.jobs) > 50:
        raise HTTPException(400, "Too many jobs in a single batch (max 50)")

    valid_channels = {a.get("id") for a in get_accounts("youtube")}
    out: list[dict] = []
    for item in payload.jobs:
        if item.channel_id not in valid_channels:
            out.append({
                "channel_id": item.channel_id,
                "ok": False,
                "error": "channel not found",
            })
            continue
        if item.kind not in ("short", "long"):
            out.append({
                "channel_id": item.channel_id,
                "ok": False,
                "error": f"invalid kind {item.kind!r}",
            })
            continue
        if item.kind == "short" and item.render_profile and item.render_profile not in ("quality", "fast", "turbo"):
            out.append({
                "channel_id": item.channel_id,
                "ok": False,
                "error": f"invalid render_profile {item.render_profile!r}",
            })
            continue

        ch = next((a for a in get_accounts("youtube") if a.get("id") == item.channel_id), None)
        args = [
            "generate",
            "--channel-id", item.channel_id,
            "--kind", item.kind,
            "--image-mode", item.image_mode or "ai",
        ]
        if item.custom_topic:
            args += ["--topic", item.custom_topic]
        if item.auto_upload:
            args += ["--upload"]
        if item.series_id:
            args += ["--series-id", item.series_id]
        if item.model:
            args += ["--model", item.model]
        if item.sentence_length and item.sentence_length > 0:
            args += ["--sentence-length", str(item.sentence_length)]
        if item.hook_style:
            args += ["--hook-style", item.hook_style]
        if item.kind == "short" and item.render_profile:
            args += ["--render-profile", item.render_profile]

        nick = (ch or {}).get("nickname", item.channel_id)
        label = "Short" if item.kind == "short" else "Long"
        title = f"[Batch] {label} — {nick}"
        job = _spawn_job(args, title=title, channel_id=item.channel_id, kind=item.kind)
        out.append({
            "channel_id": item.channel_id,
            "channel_nickname": nick,
            "kind": item.kind,
            "job_id": job.id,
            "ok": True,
        })

    return {"jobs": out, "spawned": sum(1 for j in out if j.get("ok"))}


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


@app.get("/api/youtube/sync")
async def sync_youtube(
    channel_id: str = "",
    prune: bool = True,
    add_missing: bool = True,
    refresh_meta: bool = True,
):
    """Run scripts/sync_youtube_cache.py against either one channel or all of
    them. Streams the per-video progress as SSE so the UI can show it live.
    """
    args = ["sync-yt"]
    if prune:
        args.append("--prune")
    if add_missing:
        args.append("--add-missing")
    if refresh_meta:
        args.append("--refresh-meta")
    if channel_id:
        ch = next((a for a in get_accounts("youtube") if a.get("id") == channel_id), None)
        if not ch:
            raise HTTPException(404, "Channel not found")
        args += ["--channel-id", channel_id]
        title = f"Sync YouTube — {ch.get('nickname', channel_id)}"
    else:
        title = "Sync YouTube — todos los canales"
    job = _spawn_job(args, title=title)
    return EventSourceResponse(_stream_job(job))


# ---------------------------------------------------------------------------
# Auto-sync scheduler endpoints
# ---------------------------------------------------------------------------

@app.get("/api/auto-sync/status")
def auto_sync_status():
    """Return the current state of all three tiers + their config. The UI
    polls this every few seconds so the user can see "next sync in 12 min"
    live without holding a websocket open."""
    if _auto_sync_scheduler is None:
        return {"running": False, "tiers": {}, "config": {}, "logs": {}}
    return _auto_sync_scheduler.get_state()


@app.post("/api/auto-sync/run/{tier}")
async def auto_sync_run_now(tier: str):
    """Force a specific tier to run immediately — interrupts whatever wait
    is in progress without changing the configured interval."""
    if _auto_sync_scheduler is None:
        raise HTTPException(503, "Scheduler not initialized")
    if tier not in ("light", "recent", "full"):
        raise HTTPException(400, f"Unknown tier {tier!r}")
    await _auto_sync_scheduler.trigger_now(tier)
    return {"ok": True, "tier": tier}


class AutoSyncConfig(BaseModel):
    enabled: Optional[bool] = None
    light_enabled: Optional[bool] = None
    light_interval_minutes: Optional[int] = None
    recent_enabled: Optional[bool] = None
    recent_interval_minutes: Optional[int] = None
    recent_video_count: Optional[int] = None
    full_enabled: Optional[bool] = None
    full_interval_minutes: Optional[int] = None


@app.put("/api/auto-sync/config")
def auto_sync_update_config(payload: AutoSyncConfig):
    """Patch the auto_sync block in config.json. Only the fields the user
    explicitly sets get written — leaves other keys alone. The scheduler
    re-reads config every cycle, so changes apply within ~1 min."""
    current = _read_config()
    sub = current.get("auto_sync") or {}
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    sub.update(patch)
    current["auto_sync"] = sub
    _write_config(current)
    return {"ok": True, "auto_sync": sub}


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

def _normalize_title_for_match(t: str) -> str:
    """Lowercase + strip accents/punct + collapse whitespace. Used to reconcile
    a generated video's sidecar title against the youtube.json history."""
    if not t:
        return ""
    import unicodedata as _ud
    s = _ud.normalize("NFD", t)
    s = "".join(c for c in s if _ud.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _published_titles_index() -> dict:
    """Return {normalized_title: youtube_url} across every channel's videos[]
    that has a real YouTube URL. Used to verify that a manifest still flagged
    `uploaded:false` actually made it onto YouTube under that title."""
    raw = _read_youtube_raw()
    idx: dict = {}
    for acc in raw.get("accounts", []) or []:
        for v in acc.get("videos", []) or []:
            url = v.get("url", "") or ""
            if not url.startswith("http"):
                continue
            tnorm = _normalize_title_for_match(v.get("title", ""))
            if tnorm and tnorm not in idx:
                idx[tnorm] = url
    return idx


@app.get("/api/storage/mp4")
def list_mp4():
    if not MP_DIR.exists():
        return []
    out = []
    pub_idx: Optional[dict] = None  # built lazily, only if we hit a pending file
    for p in MP_DIR.iterdir():
        if p.suffix.lower() == ".mp4":
            try:
                stat = p.stat()
                # Read upload state from the per-video manifest sidecar written
                # by `record_generation()`/`mark_uploaded()` in upload_tracker.
                manifest_path = MP_DIR / f"{p.stem}.manifest.json"
                uploaded = False
                uploaded_url: Optional[str] = None
                subject: Optional[str] = None
                if manifest_path.exists():
                    try:
                        with manifest_path.open("r", encoding="utf-8") as fh:
                            mdata = json.load(fh) or {}
                        uploaded = bool(mdata.get("uploaded"))
                        uploaded_url = mdata.get("uploaded_url") or None
                        subject = mdata.get("subject") or None
                    except Exception:
                        mdata = None

                # Reconciliation pass: a manifest can stay `uploaded:false`
                # forever if Selenium loses sync with Firefox during the
                # upload — the file ends up on YouTube but mark_uploaded()
                # never runs. Compare the upload-sidecar title against the
                # youtube.json history; if it matches a published video,
                # persist the flip so subsequent listings are fast.
                if not uploaded and manifest_path.exists():
                    sidecar_path = MP_DIR / f"{p.stem}.meta.json"
                    if sidecar_path.exists():
                        try:
                            with sidecar_path.open("r", encoding="utf-8") as fh:
                                sdata = json.load(fh) or {}
                            stitle = (sdata.get("metadata") or {}).get("title", "")
                            tnorm = _normalize_title_for_match(stitle)
                            if tnorm:
                                if pub_idx is None:
                                    pub_idx = _published_titles_index()
                                hit = pub_idx.get(tnorm)
                                if hit:
                                    try:
                                        cur = mdata or {}
                                        cur["uploaded"] = True
                                        cur["uploaded_url"] = hit
                                        cur["uploaded_at"] = datetime.utcnow().isoformat() + "Z"
                                        with manifest_path.open("w", encoding="utf-8") as fh:
                                            json.dump(cur, fh, indent=2)
                                        uploaded = True
                                        uploaded_url = hit
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                out.append({
                    "name": p.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 1),
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "uploaded": uploaded,
                    "uploaded_url": uploaded_url,
                    "subject": subject,
                })
            except OSError:
                pass
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


@app.post("/api/storage/mp4/{filename}/mark-uploaded")
def mark_uploaded_mp4(filename: str, url: Optional[str] = None):
    """Manual override for the case where the auto-reconciliation in
    `/api/storage/mp4` can't find a title match (user edited the title on
    YouTube, video isn't on the right channel's history yet, etc.)."""
    target = MP_DIR / filename
    if target.parent != MP_DIR or not target.exists() or target.suffix.lower() != ".mp4":
        raise HTTPException(404, "File not found")
    manifest_path = MP_DIR / f"{target.stem}.manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, "Manifest not found for this video")
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
        data["uploaded"] = True
        if url:
            data["uploaded_url"] = url
        data["uploaded_at"] = datetime.utcnow().isoformat() + "Z"
        with manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as e:
        raise HTTPException(500, f"Failed to update manifest: {e}")
    return {"ok": True, "uploaded_url": data.get("uploaded_url")}


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
