"""
Crash-resume checkpoints for the YouTube generation pipeline.

One JSON file per run at .mp/checkpoints/<run_id>.json. After every pipeline
stage YouTube saves the accumulated state; if the process dies, resume_video.py
can rehydrate it and continue from the last completed stage.

All writes are best-effort: if a checkpoint write fails, the running pipeline
must NOT abort. Likewise, all reads tolerate corrupt or partial files.
"""
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from config import ROOT_DIR


CHECKPOINT_DIR = os.path.join(ROOT_DIR, ".mp", "checkpoints")

# Pipeline stages, in order. Resume jumps to the first stage AFTER `stage`.
STAGES_LONG = [
    "topic", "script", "metadata", "thumbnail",
    "prompts", "images", "tts", "combine", "uploaded",
]
STAGES_SHORT = [
    "topic", "script", "metadata",
    "prompts", "images", "tts", "combine", "uploaded",
]


def _ensure_dir() -> None:
    try:
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    except Exception:
        pass


def _path(run_id: str) -> str:
    return os.path.join(CHECKPOINT_DIR, f"{run_id}.json")


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def start_run(account_uuid: str, video_type: str, params: Optional[Dict] = None) -> str:
    """Create a fresh checkpoint and return its run_id."""
    run_id = str(uuid4())
    _ensure_dir()
    state = {
        "run_id": run_id,
        "account_uuid": account_uuid,
        "video_type": video_type,  # "long" | "short"
        "started_at": _now(),
        "updated_at": _now(),
        "stage": None,
        "status": "in_progress",
        "error": None,
        "params": params or {},
        "data": {},
    }
    _write(run_id, state)
    return run_id


def save_stage(run_id: Optional[str], stage: str, data: Dict) -> None:
    """Merge `data` into the checkpoint and mark `stage` as completed.

    Silent: any error here must NOT bubble up — checkpointing is best-effort.
    """
    if not run_id:
        return
    try:
        state = load(run_id) or {}
        state.setdefault("data", {}).update(data or {})
        state["stage"] = stage
        state["updated_at"] = _now()
        state["status"] = "in_progress"
        state["error"] = None
        _write(run_id, state)
    except Exception:
        pass


def mark_failed(run_id: Optional[str], stage: str, exc: BaseException) -> None:
    if not run_id:
        return
    try:
        state = load(run_id) or {}
        state["status"] = "failed"
        state["updated_at"] = _now()
        state["error"] = {
            "stage": stage,
            "message": str(exc)[:500],
            "type": type(exc).__name__,
            "traceback": traceback.format_exc()[-2000:],
        }
        _write(run_id, state)
    except Exception:
        pass


def mark_completed(run_id: Optional[str]) -> None:
    if not run_id:
        return
    try:
        state = load(run_id) or {}
        state["status"] = "completed"
        state["stage"] = "uploaded"
        state["updated_at"] = _now()
        state["error"] = None
        _write(run_id, state)
    except Exception:
        pass


def load(run_id: str) -> Optional[Dict]:
    path = _path(run_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_all() -> List[Dict]:
    """Return every checkpoint, newest first."""
    _ensure_dir()
    out = []
    try:
        for fname in os.listdir(CHECKPOINT_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(CHECKPOINT_DIR, fname), "r", encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                continue
    except Exception:
        pass
    out.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return out


def list_pending() -> List[Dict]:
    """Checkpoints in 'in_progress' or 'failed' state — candidates for resume."""
    return [s for s in list_all() if s.get("status") in ("in_progress", "failed")]


def delete(run_id: str) -> bool:
    try:
        os.remove(_path(run_id))
        return True
    except Exception:
        return False


def get_protected_paths() -> set:
    """Asset paths referenced by any active (in_progress|failed) checkpoint.

    rem_temp_files() reads this and skips these files so a crashed run can
    still be resumed from its partial assets.
    """
    protected = set()
    for state in list_pending():
        data = state.get("data") or {}
        for key in ("tts_path", "thumbnail_path", "video_path", "subtitles_path"):
            v = data.get(key)
            if isinstance(v, str) and v:
                protected.add(os.path.abspath(v))
        for img in (data.get("images") or []):
            if isinstance(img, str) and img:
                protected.add(os.path.abspath(img))
    return protected


def _write(run_id: str, state: Dict) -> None:
    """Atomic write: tmp file + os.replace. Never partial JSON on disk."""
    _ensure_dir()
    final = _path(run_id)
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, final)
