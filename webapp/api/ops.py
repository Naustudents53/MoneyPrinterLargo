"""
MoneyPrinter Largo — Operations / Observability module.

Exposes endpoints for:
  - Disk monitor:    GET /api/ops/disk
  - Cost tracking:   GET /api/ops/cost           (read aggregated)
                     POST /api/ops/cost/log      (internal: append entry)
                     DELETE /api/ops/cost        (reset)
  - Error dashboard: GET    /api/ops/errors
                     GET    /api/ops/errors/{name}/{file}    (raw screenshot/html)
                     DELETE /api/ops/errors/{name}
                     POST   /api/ops/errors/clear
  - Job log:         GET    /api/ops/job-log     (persisted history)
                     DELETE /api/ops/job-log
  - Notifications:   GET /api/ops/notifications  (read webhook config)
                     PUT /api/ops/notifications  (write webhook config)
                     POST /api/ops/notifications/test
  - Backup/restore:  GET  /api/ops/backup        (stream zip)
                     POST /api/ops/restore       (accept zip, restore)

State files (under .mp/):
  - cost_log.jsonl       — one JSON line per LLM/image API call
  - job_log.jsonl        — one JSON line per finished job
  - ops_settings.json    — webhook URLs + thresholds
"""
from __future__ import annotations

import io
import json
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel


# Resolved at runtime by main.py via init().
_ROOT_DIR: Optional[Path] = None
_MP_DIR: Optional[Path] = None
_CONFIG_PATH: Optional[Path] = None

router = APIRouter(prefix="/api/ops", tags=["ops"])


def init(root_dir: Path, mp_dir: Path, config_path: Path) -> None:
    """Bind the module to the host app's paths. Called once from main.py."""
    global _ROOT_DIR, _MP_DIR, _CONFIG_PATH
    _ROOT_DIR = root_dir
    _MP_DIR = mp_dir
    _CONFIG_PATH = config_path
    _MP_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

def _cost_log_path() -> Path:
    return _MP_DIR / "cost_log.jsonl"


def _job_log_path() -> Path:
    return _MP_DIR / "job_log.jsonl"


def _settings_path() -> Path:
    return _MP_DIR / "ops_settings.json"


def _failures_dir() -> Path:
    return _MP_DIR / "upload_failures"


def _temp_dir() -> Path:
    return _MP_DIR / "tmp"


# ---------------------------------------------------------------------------
# 1) Disk monitor
# ---------------------------------------------------------------------------

@router.get("/disk")
def disk_usage():
    """Walk .mp/ and return total bytes, breakdown by extension, biggest files,
    and an oldest-first sample. Cheap enough to call on page focus."""
    root = _MP_DIR
    if not root or not root.exists():
        return {"total_bytes": 0, "files": 0, "by_ext": {}, "biggest": [], "oldest": None}

    total = 0
    file_count = 0
    by_ext: dict[str, dict[str, int]] = {}
    rows: list[dict] = []

    for dp, _, fns in os.walk(root):
        for fn in fns:
            full = os.path.join(dp, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            size = st.st_size
            mtime = st.st_mtime
            ext = (os.path.splitext(fn)[1] or "(none)").lower()
            total += size
            file_count += 1
            entry = by_ext.setdefault(ext, {"bytes": 0, "count": 0})
            entry["bytes"] += size
            entry["count"] += 1
            rel = os.path.relpath(full, root)
            rows.append({"path": rel.replace("\\", "/"), "bytes": size, "mtime": mtime})

    rows.sort(key=lambda r: r["bytes"], reverse=True)
    biggest = rows[:25]
    oldest = min(rows, key=lambda r: r["mtime"]) if rows else None

    by_ext_list = sorted(
        [{"ext": e, **v} for e, v in by_ext.items()],
        key=lambda x: x["bytes"], reverse=True,
    )

    try:
        free = shutil.disk_usage(str(root)).free
    except OSError:
        free = -1

    return {
        "total_bytes": total,
        "files": file_count,
        "by_ext": by_ext_list,
        "biggest": biggest,
        "oldest": oldest,
        "disk_free_bytes": free,
    }


@router.post("/disk/clear-temp")
def clear_temp():
    """Delete scratch files in .mp/tmp plus legacy root WAV/PNG/SRT/JPG files."""
    if not _MP_DIR or not _MP_DIR.exists():
        return {"deleted": 0}
    deleted = 0
    bytes_freed = 0

    temp = _temp_dir()
    if temp.exists():
        for dp, _, fns in os.walk(temp):
            for fn in fns:
                full = Path(dp) / fn
                try:
                    bytes_freed += full.stat().st_size
                    full.unlink()
                    deleted += 1
                except OSError:
                    pass

    for fn in os.listdir(_MP_DIR):
        full = _MP_DIR / fn
        if not full.is_file():
            continue
        ext = full.suffix.lower()
        if ext in {".wav", ".png", ".srt", ".jpg", ".jpeg", ".txt", ".log"}:
            try:
                bytes_freed += full.stat().st_size
                full.unlink()
                deleted += 1
            except OSError:
                pass
    return {"deleted": deleted, "bytes_freed": bytes_freed}


# ---------------------------------------------------------------------------
# 2) Cost tracking
# ---------------------------------------------------------------------------

# Pricing in USD per 1M tokens (input, output). Conservative defaults — user
# can adjust by editing the table or supplying overrides in ops_settings.json.
_GEMINI_PRICING = {
    "gemini-2.5-flash":      {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.075, "out": 0.30},
    "gemini-2.5-pro":        {"in": 1.25, "out": 10.00},
    "gemini-1.5-flash":      {"in": 0.075, "out": 0.30},
    "gemini-1.5-pro":        {"in": 1.25, "out": 5.00},
    "gemini-2.0-flash":      {"in": 0.10, "out": 0.40},
}
# Per-call estimate when the underlying API doesn't report tokens.
_FALLBACK_COST_USD = 0.0005


def estimate_gemini_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _GEMINI_PRICING.get(model)
    if not p:
        # Try a prefix match (e.g. "gemini-2.5-flash-002" → "gemini-2.5-flash")
        for k, v in _GEMINI_PRICING.items():
            if model.startswith(k):
                p = v
                break
    if not p:
        return _FALLBACK_COST_USD
    return (in_tokens / 1_000_000) * p["in"] + (out_tokens / 1_000_000) * p["out"]


def append_cost_entry(entry: dict) -> None:
    """Append a single cost record. Used both by the HTTP endpoint and the
    in-process logger (observability.py)."""
    if not _MP_DIR:
        return
    _MP_DIR.mkdir(parents=True, exist_ok=True)
    entry.setdefault("ts", time.time())
    line = json.dumps(entry, ensure_ascii=False)
    try:
        with open(_cost_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class CostEntryIn(BaseModel):
    provider: str            # "gemini" | "huggingface" | "ollama" | ...
    model: str = ""
    kind: str = "text"       # "text" | "image" | "audio"
    in_tokens: int = 0
    out_tokens: int = 0
    cost_usd: float = 0.0
    channel_id: str = ""
    note: str = ""


@router.post("/cost/log")
def log_cost(payload: CostEntryIn):
    entry = payload.model_dump()
    if entry["cost_usd"] == 0.0 and entry["provider"] == "gemini":
        entry["cost_usd"] = estimate_gemini_cost(
            entry["model"], entry["in_tokens"], entry["out_tokens"],
        )
    append_cost_entry(entry)
    return {"ok": True, "cost_usd": entry["cost_usd"]}


@router.get("/cost")
def cost_summary(days: int = 30):
    """Aggregate cost log into per-day, per-provider, per-model totals."""
    path = _cost_log_path()
    if not path.exists():
        return {
            "total_usd": 0.0, "total_calls": 0, "by_day": [],
            "by_provider": [], "by_model": [], "by_channel": [], "recent": [],
        }
    cutoff = time.time() - days * 86400
    by_day: dict[str, dict[str, float]] = {}
    by_provider: dict[str, dict[str, float]] = {}
    by_model: dict[str, dict[str, float]] = {}
    by_channel: dict[str, dict[str, float]] = {}
    total_usd = 0.0
    total_calls = 0
    recent: list[dict] = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = e.get("ts", 0)
            if ts < cutoff:
                continue
            cost = float(e.get("cost_usd", 0.0))
            day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            for bucket, key in (
                (by_day, day),
                (by_provider, e.get("provider", "unknown")),
                (by_model, e.get("model", "") or "(unspecified)"),
                (by_channel, e.get("channel_id") or "(none)"),
            ):
                slot = bucket.setdefault(key, {"cost_usd": 0.0, "calls": 0})
                slot["cost_usd"] += cost
                slot["calls"] += 1
            total_usd += cost
            total_calls += 1
            if len(recent) < 50:
                recent.append(e)

    def to_list(d: dict, key_name: str) -> list[dict]:
        return sorted(
            [{key_name: k, **v} for k, v in d.items()],
            key=lambda x: x["cost_usd"], reverse=True,
        )

    # by_day sorted ascending by date for charting
    by_day_list = sorted(
        [{"day": k, **v} for k, v in by_day.items()],
        key=lambda x: x["day"],
    )
    return {
        "total_usd": round(total_usd, 4),
        "total_calls": total_calls,
        "by_day": by_day_list,
        "by_provider": to_list(by_provider, "provider"),
        "by_model": to_list(by_model, "model"),
        "by_channel": to_list(by_channel, "channel_id"),
        "recent": list(reversed(recent[-50:])),
    }


@router.delete("/cost")
def reset_cost():
    p = _cost_log_path()
    if p.exists():
        p.unlink()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 3) Error dashboard (upload_failures/)
# ---------------------------------------------------------------------------

def _parse_failure_name(name: str) -> dict:
    """Names look like '20260502_201211__thumbnail_upload_failed' or
    '..._exception_NoSuchWindowException'. Extract a timestamp + tag."""
    out = {"raw": name, "ts": 0.0, "tag": name}
    parts = name.split("__", 1)
    if len(parts) == 2 and len(parts[0]) >= 13:
        try:
            dt = datetime.strptime(parts[0], "%Y%m%d_%H%M%S")
            out["ts"] = dt.timestamp()
            out["tag"] = parts[1]
        except ValueError:
            pass
    return out


@router.get("/errors")
def list_errors():
    fdir = _failures_dir()
    if not fdir.exists():
        return {"items": [], "total": 0}
    items = []
    for d in fdir.iterdir():
        if not d.is_dir():
            continue
        meta = _parse_failure_name(d.name)
        size = 0
        files = []
        for sub in d.iterdir():
            if sub.is_file():
                try:
                    sz = sub.stat().st_size
                except OSError:
                    sz = 0
                size += sz
                files.append({"name": sub.name, "bytes": sz})
        # Pull a context snippet if present.
        ctx_snippet = ""
        ctx_path = d / "context.txt"
        if ctx_path.exists():
            try:
                with open(ctx_path, "r", encoding="utf-8", errors="replace") as f:
                    ctx_snippet = f.read(800)
            except OSError:
                pass
        items.append({
            "name": d.name,
            "tag": meta["tag"],
            "ts": meta["ts"] or d.stat().st_mtime,
            "size_bytes": size,
            "files": sorted(files, key=lambda x: x["name"]),
            "context": ctx_snippet,
        })
    items.sort(key=lambda x: x["ts"], reverse=True)
    # Group counts by tag for a "top error types" widget.
    tags: dict[str, int] = {}
    for it in items:
        tags[it["tag"]] = tags.get(it["tag"], 0) + 1
    by_tag = sorted(
        [{"tag": k, "count": v} for k, v in tags.items()],
        key=lambda x: x["count"], reverse=True,
    )
    return {"items": items, "total": len(items), "by_tag": by_tag}


def _safe_failure_path(name: str, file: str) -> Path:
    fdir = _failures_dir()
    target = (fdir / name / file).resolve()
    if not str(target).startswith(str(fdir.resolve())):
        raise HTTPException(400, "Path traversal denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Not found")
    return target


@router.get("/errors/{name}/file/{file}")
def get_error_file(name: str, file: str):
    p = _safe_failure_path(name, file)
    return FileResponse(str(p))


@router.delete("/errors/{name}")
def delete_error(name: str):
    fdir = _failures_dir()
    target = (fdir / name).resolve()
    if not str(target).startswith(str(fdir.resolve())):
        raise HTTPException(400, "Path traversal denied")
    if not target.exists():
        raise HTTPException(404, "Not found")
    shutil.rmtree(target, ignore_errors=True)
    return {"ok": True}


@router.post("/errors/clear")
def clear_errors():
    fdir = _failures_dir()
    if not fdir.exists():
        return {"deleted": 0}
    n = 0
    for d in list(fdir.iterdir()):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return {"deleted": n}


# ---------------------------------------------------------------------------
# 4) Job log (persisted history)
# ---------------------------------------------------------------------------

def append_job_record(record: dict) -> None:
    """Called from main.py when a JobState transitions to a terminal state.
    Persists a one-line summary so the Logs page survives backend restarts."""
    if not _MP_DIR:
        return
    _MP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(_job_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


@router.get("/job-log")
def job_log(q: str = "", status: str = "", channel_id: str = "",
            limit: int = 200):
    """Search past jobs. q matches title/last_line, status is 'done|error',
    channel_id filters by YouTube channel. Returns newest-first."""
    p = _job_log_path()
    if not p.exists():
        return {"items": [], "total": 0}
    items: list[dict] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if status and r.get("status") != status:
                continue
            if channel_id and r.get("channel_id") != channel_id:
                continue
            if q:
                hay = (r.get("title", "") + " " + r.get("last_line", "")).lower()
                if q.lower() not in hay:
                    continue
            items.append(r)
    items.reverse()
    return {"items": items[:limit], "total": len(items)}


@router.get("/job-log/{job_id}")
def job_log_detail(job_id: str):
    """Return the full log lines for a finished job, if persisted."""
    detail_path = _MP_DIR / "job_logs" / f"{job_id}.log"
    if not detail_path.exists():
        raise HTTPException(404, "No persisted log for this job")
    try:
        with open(detail_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        raise HTTPException(500, "Could not read log")
    return {"job_id": job_id, "content": content}


@router.delete("/job-log")
def clear_job_log():
    p = _job_log_path()
    if p.exists():
        p.unlink()
    detail_dir = _MP_DIR / "job_logs"
    if detail_dir.exists():
        shutil.rmtree(detail_dir, ignore_errors=True)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 5) Notifications (Discord / Telegram webhooks)
# ---------------------------------------------------------------------------

class NotifSettings(BaseModel):
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    on_done: bool = True
    on_error: bool = True
    disk_threshold_gb: float = 0.0   # 0 = disabled


def _read_settings() -> dict:
    p = _settings_path()
    if not p.exists():
        return NotifSettings().model_dump()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = NotifSettings().model_dump()
        merged.update({k: v for k, v in data.items() if k in merged})
        return merged
    except (OSError, json.JSONDecodeError):
        return NotifSettings().model_dump()


def _write_settings(data: dict) -> None:
    if not _MP_DIR:
        return
    _MP_DIR.mkdir(parents=True, exist_ok=True)
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/notifications")
def get_notifications():
    return _read_settings()


@router.put("/notifications")
def put_notifications(payload: NotifSettings):
    data = payload.model_dump()
    _write_settings(data)
    return data


def fire_webhook(message: str, level: str = "info") -> dict:
    """Send `message` to whichever webhooks are configured. `level` is one of
    'info' | 'success' | 'error'. Failures are swallowed — observability must
    not break business flow."""
    s = _read_settings()
    results = {"discord": None, "telegram": None}
    icon = {"info": "ℹ️", "success": "✅", "error": "❌"}.get(level, "•")
    text = f"{icon} {message}"

    if s.get("discord_webhook_url"):
        try:
            r = requests.post(
                s["discord_webhook_url"],
                json={"content": text[:1900]},
                timeout=8,
            )
            results["discord"] = {"ok": r.ok, "status": r.status_code}
        except Exception as e:
            results["discord"] = {"ok": False, "error": str(e)[:200]}

    if s.get("telegram_bot_token") and s.get("telegram_chat_id"):
        try:
            url = f"https://api.telegram.org/bot{s['telegram_bot_token']}/sendMessage"
            r = requests.post(
                url,
                json={"chat_id": s["telegram_chat_id"], "text": text[:4000]},
                timeout=8,
            )
            results["telegram"] = {"ok": r.ok, "status": r.status_code}
        except Exception as e:
            results["telegram"] = {"ok": False, "error": str(e)[:200]}

    return results


@router.post("/notifications/test")
def test_notifications():
    res = fire_webhook("MoneyPrinter — test notification", level="info")
    return res


def maybe_notify_job_finished(record: dict) -> None:
    """Wired from main.py via `_finish_hook`. Decides whether to fire based on
    user prefs and the job's status."""
    s = _read_settings()
    status = record.get("status", "")
    if status == "done" and not s.get("on_done", True):
        return
    if status == "error" and not s.get("on_error", True):
        return
    if status not in ("done", "error"):
        return
    title = record.get("title", "job")
    elapsed = record.get("elapsed", 0)
    last = record.get("last_line", "")
    msg = (
        f"**{title}** — {status} in {elapsed}s\n"
        f"`{last[:300]}`"
    )
    fire_webhook(msg, level="success" if status == "done" else "error")


# ---------------------------------------------------------------------------
# 6) Backup / restore
# ---------------------------------------------------------------------------

def _iter_backup_paths(include_videos: bool):
    """Yield (absolute_path, arcname) tuples for the backup zip."""
    if _CONFIG_PATH and _CONFIG_PATH.exists():
        yield _CONFIG_PATH, "config.json"
    if not _MP_DIR or not _MP_DIR.exists():
        return
    skip_roots = {
        _temp_dir().resolve(),
        (_MP_DIR / "photo_uploads").resolve(),
        (_MP_DIR / "job_logs").resolve(),
        (_MP_DIR / "jobs").resolve(),
        (_MP_DIR / "checkpoints").resolve(),
    }
    for dp, dirs, fns in os.walk(_MP_DIR):
        dirs[:] = [
            d for d in dirs
            if (Path(dp) / d).resolve() not in skip_roots
        ]
        for fn in fns:
            full = Path(dp) / fn
            ext = full.suffix.lower()
            rel = full.relative_to(_MP_DIR)
            in_videos = rel.parts and rel.parts[0] == "videos"
            if in_videos and not include_videos:
                continue
            if ext == ".mp4" and not include_videos:
                continue
            if ext not in {".json", ".jsonl", ".mp4"}:
                continue
            arc = "mp/" + str(full.relative_to(_MP_DIR)).replace("\\", "/")
            yield full, arc


@router.get("/backup")
def backup(include_videos: bool = False):
    """Stream a zip with config.json + .mp/ JSON state. Optionally includes
    the .mp4 video files (off by default — they can be tens of GB)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for full, arc in _iter_backup_paths(include_videos):
            try:
                zf.write(full, arc)
            except OSError:
                pass
        manifest = {
            "created_at": datetime.now().isoformat(),
            "include_videos": include_videos,
            "version": "1",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    buf.seek(0)
    fname = f"mpl-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/restore")
async def restore(file: UploadFile = File(...), wipe: bool = False):
    """Accept a zip produced by /api/ops/backup and restore it.

    `wipe=true` removes existing JSON state in `.mp/` (NOT mp4s) before
    extracting — useful when restoring to a clean machine. Default is merge.
    """
    if not _MP_DIR or not _CONFIG_PATH:
        raise HTTPException(500, "Backend paths not initialized")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Not a valid zip file")

    names = zf.namelist()
    if "manifest.json" not in names:
        raise HTTPException(400, "Zip is missing manifest.json — not an MPL backup")

    if wipe:
        # Remove only state JSON files; preserve videos and subdirs to avoid
        # surprise data loss.
        for fn in os.listdir(_MP_DIR):
            full = _MP_DIR / fn
            if full.is_file() and full.suffix.lower() == ".json":
                try:
                    full.unlink()
                except OSError:
                    pass

    extracted = 0
    skipped = 0
    for n in names:
        if n == "manifest.json":
            continue
        # Path-traversal guard.
        if ".." in n.replace("\\", "/").split("/"):
            skipped += 1
            continue
        if n == "config.json":
            target = _CONFIG_PATH
        elif n.startswith("mp/"):
            target = _MP_DIR / n[3:]
        else:
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zf.open(n) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1
        except OSError:
            skipped += 1
    return {"extracted": extracted, "skipped": skipped, "wiped": wipe}
