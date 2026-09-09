"""
Higgsfield Long Video Studio — FastAPI router.

Provides REST + SSE endpoints for the cinematic production pipeline.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Path bootstrap (same as main.py)
# ---------------------------------------------------------------------------
API_DIR = Path(__file__).resolve().parent
ROOT_DIR = API_DIR.parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

router = APIRouter(prefix="/api/higgsfield", tags=["higgsfield"])

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class NewProductionIn(BaseModel):
    title: str = ""
    topic: str
    target_duration_min: float = 15.0
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    language: str = "es"
    narrator_voice: str = ""
    style: str = "documentary"
    genre: str = "documentary"
    quality: str = "quality"
    provider: str = "higgsfield"
    research_mode: str = "light"
    director_mode: str = "auto"
    production_mode: str = "full"
    budget_limit: float | None = None
    auto_upload: bool = False
    channel_id: str = ""
    series_id: str = ""
    dry_run: bool = False


class ShotActionIn(BaseModel):
    action: str  # approve, reject, regenerate, edit_prompt
    prompt: str | None = None
    model_id: str | None = None


class BudgetUpdateIn(BaseModel):
    budget_limit: float


# ---------------------------------------------------------------------------
# Storage helper
# ---------------------------------------------------------------------------
_storage = None


def _get_storage():
    global _storage
    if _storage is None:
        from higgsfield_studio.storage import get_storage
        _storage = get_storage()
    return _storage


# ---------------------------------------------------------------------------
# Active jobs registry
# ---------------------------------------------------------------------------
_jobs: dict[str, dict] = {}
_job_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Routes — Projects
# ---------------------------------------------------------------------------

@router.get("/projects")
def list_projects(limit: int = 50, offset: int = 0):
    return _get_storage().list_projects(limit, offset)


@router.post("/projects")
def create_project(body: NewProductionIn):
    from higgsfield_studio.models import (
        ProductionProject, ProjectConfig, QualityMode,
        DirectorMode, ProductionMode,
    )

    quality_map = {"budget": QualityMode.BUDGET, "balanced": QualityMode.BALANCED,
                   "quality": QualityMode.QUALITY, "cinema": QualityMode.CINEMA}
    director_map = {"auto": DirectorMode.AUTO, "director": DirectorMode.DIRECTOR}
    mode_map = {"plan": ProductionMode.PLAN, "plan_prompts": ProductionMode.PLAN_PROMPTS,
                "full": ProductionMode.FULL, "upgrade": ProductionMode.UPGRADE,
                "regenerate_failed": ProductionMode.REGENERATE_FAILED,
                "render_only": ProductionMode.RENDER_ONLY}

    config = ProjectConfig(
        title=body.title or body.topic[:60],
        topic=body.topic,
        target_duration_min=body.target_duration_min,
        aspect_ratio=body.aspect_ratio,
        resolution=body.resolution,
        language=body.language,
        narrator_voice=body.narrator_voice,
        style=body.style,
        genre=body.genre,
        quality=quality_map.get(body.quality, QualityMode.QUALITY),
        provider=body.provider,
        research_mode=body.research_mode,
        director_mode=director_map.get(body.director_mode, DirectorMode.AUTO),
        production_mode=mode_map.get(body.production_mode, ProductionMode.FULL),
        budget_limit=body.budget_limit,
        auto_upload=body.auto_upload,
        channel_id=body.channel_id,
        series_id=body.series_id,
        dry_run=body.dry_run,
    )

    project = ProductionProject(config=config)
    _get_storage().save_project(project)
    return {"id": project.id, "phase": project.phase.value}


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project.to_dict()


@router.delete("/projects/{project_id}")
def delete_project(project_id: str):
    if _get_storage().delete_project(project_id):
        return {"deleted": True}
    raise HTTPException(404, "Project not found")


# ---------------------------------------------------------------------------
# Routes — Production pipeline (SSE)
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/run")
async def run_production(project_id: str):
    """Start or resume a production pipeline. Returns SSE stream."""
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    job_id = uuid.uuid4().hex[:12]
    events: list[dict] = []
    finished = threading.Event()
    error_holder: list[str] = []

    def on_event(event_type: str, data: dict):
        events.append({"event": event_type, "data": data, "ts": time.time()})

    def run_in_thread():
        try:
            from higgsfield_studio.orchestrator import ProductionOrchestrator
            orch = ProductionOrchestrator(storage=_get_storage(), on_event=on_event)
            with _job_lock:
                _jobs[job_id] = {"orchestrator": orch, "project_id": project_id, "started": time.time()}
            orch.run_production(project)
        except Exception as e:
            error_holder.append(str(e))
            on_event("error", {"message": str(e)})
        finally:
            finished.set()
            with _job_lock:
                _jobs.pop(job_id, None)

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    async def stream() -> AsyncIterator[dict]:
        cursor = 0
        yield {"event": "start", "data": json.dumps({"job_id": job_id, "project_id": project_id})}
        while not finished.is_set() or cursor < len(events):
            while cursor < len(events):
                ev = events[cursor]
                cursor += 1
                yield {"event": ev["event"], "data": json.dumps(ev["data"])}
            if not finished.is_set():
                await asyncio.sleep(0.3)
        yield {"event": "done", "data": json.dumps({"job_id": job_id, "error": error_holder[0] if error_holder else None})}

    return EventSourceResponse(stream())


@router.post("/projects/{project_id}/cancel")
def cancel_production(project_id: str):
    with _job_lock:
        for jid, info in _jobs.items():
            if info["project_id"] == project_id:
                info["orchestrator"].cancel()
                return {"cancelled": True}
    raise HTTPException(404, "No active job for this project")


# ---------------------------------------------------------------------------
# Routes — Individual components
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/script")
def get_script(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {
        "script_raw": project.script_raw,
        "narration_blocks": [b.__dict__ if hasattr(b, '__dict__') else b for b in project.narration_blocks],
        "chapters": [c.__dict__ if hasattr(c, '__dict__') else c for c in project.chapters],
        "concept": project.concept,
        "research": project.research,
    }


@router.get("/projects/{project_id}/storyboard")
def get_storyboard(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.models import _serialize
    return {
        "scenes": [_serialize(s) for s in project.scenes],
        "chapters": [_serialize(c) for c in project.chapters],
    }


@router.get("/projects/{project_id}/shots")
def get_shots(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.models import _serialize
    return {"shots": [_serialize(s) for s in project.shots]}


@router.post("/projects/{project_id}/shots/{shot_id}")
def shot_action(project_id: str, shot_id: str, body: ShotActionIn):
    from higgsfield_studio.models import ShotStatus
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    shot = next((s for s in project.shots if s.id == shot_id), None)
    if not shot:
        raise HTTPException(404, "Shot not found")

    if body.action == "approve":
        shot.status = ShotStatus.APPROVED
    elif body.action == "reject":
        shot.status = ShotStatus.REJECTED
    elif body.action == "edit_prompt":
        if body.prompt:
            shot.optimized_prompt = body.prompt
        if body.model_id:
            shot.model_id = body.model_id
    elif body.action == "regenerate":
        shot.status = ShotStatus.PLANNED
        shot.regeneration_count += 1
        if body.prompt:
            shot.optimized_prompt = body.prompt
        if body.model_id:
            shot.model_id = body.model_id
    else:
        raise HTTPException(400, f"Unknown action: {body.action}")

    _get_storage().save_project(project)
    return {"status": shot.status.value if hasattr(shot.status, 'value') else shot.status}


@router.get("/projects/{project_id}/visual-bible")
def get_visual_bible(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.models import _serialize
    return {
        "visual_bible": _serialize(project.visual_bible),
        "characters": [_serialize(c) for c in project.characters],
        "locations": [_serialize(l) for l in project.locations],
    }


@router.get("/projects/{project_id}/timeline")
def get_timeline(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.timeline import get_timeline_summary
    return {"timeline": get_timeline_summary(project)}


@router.get("/projects/{project_id}/cost")
def get_cost(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.cost import cost_summary, estimate_production_cost
    return {
        "summary": cost_summary(project),
        "estimate": estimate_production_cost(project),
    }


@router.put("/projects/{project_id}/budget")
def update_budget(project_id: str, body: BudgetUpdateIn):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project.config.budget_limit = body.budget_limit
    _get_storage().save_project(project)
    return {"budget_limit": body.budget_limit}


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str):
    return _get_storage().list_versions(project_id)


@router.get("/projects/{project_id}/manifest")
def get_manifest(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.outputs.manifest_json and os.path.exists(project.outputs.manifest_json):
        with open(project.outputs.manifest_json, encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(404, "Manifest not yet generated")


@router.get("/projects/{project_id}/rhythm")
def get_rhythm(project_id: str):
    project = _get_storage().load_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from higgsfield_studio.rhythm import get_rhythm_warnings
    from higgsfield_studio.models import _serialize
    return {
        "metrics": _serialize(project.rhythm),
        "warnings": get_rhythm_warnings(project),
    }


# ---------------------------------------------------------------------------
# Routes — Provider capabilities
# ---------------------------------------------------------------------------

@router.get("/providers")
def list_providers():
    from video_providers import list_providers as lp
    return {"providers": lp()}


@router.get("/providers/{name}/models")
async def list_models(name: str):
    from video_providers import get_provider
    try:
        provider = get_provider(name, config={"dry_run": True})
        models = await provider.list_models()
        return {"models": [m.__dict__ for m in models]}
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Routes — Prompt memory / learning
# ---------------------------------------------------------------------------

@router.get("/prompt-memory")
def get_prompt_memory(style: str = "", shot_type: str = "", limit: int = 20):
    return {"prompts": _get_storage().get_best_prompts(style, shot_type, limit)}


@router.get("/learning")
def get_learning(category: str = "", limit: int = 50):
    return {"stats": _get_storage().get_learning_stats(category, limit)}


# ---------------------------------------------------------------------------
# Routes — Genre styles catalog
# ---------------------------------------------------------------------------

@router.get("/genres")
def list_genres():
    from higgsfield_studio.models import GENRE_STYLES
    return {"genres": list(GENRE_STYLES.keys())}
