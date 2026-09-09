"""Shot planner — model routing and dependency graphs."""
from __future__ import annotations
import logging
from .models import ProductionProject, Shot, ShotType, ShotStatus, QualityMode

log = logging.getLogger(__name__)

MODEL_PREFERENCES = {
    ShotType.HERO: ["cinema", "quality"],
    ShotType.ESTABLISHING: ["cinema", "quality"],
    ShotType.AERIAL: ["quality", "cinema"],
    ShotType.CLOSE_UP: ["quality", "balanced"],
    ShotType.MEDIUM: ["balanced", "quality"],
    ShotType.WIDE: ["balanced", "quality"],
    ShotType.B_ROLL: ["balanced", "budget"],
    ShotType.TRANSITION: ["budget", "balanced"],
    ShotType.DETAIL: ["balanced", "quality"],
    ShotType.TRACKING: ["quality", "balanced"],
    ShotType.STATIC: ["balanced", "budget"],
    ShotType.DOLLY: ["quality", "balanced"],
    ShotType.HANDHELD: ["balanced", "budget"],
    ShotType.MACRO: ["quality", "balanced"],
}


def assign_models(project: ProductionProject, available_models: list[dict] | None = None) -> ProductionProject:
    quality_map = {
        QualityMode.BUDGET: "budget", QualityMode.BALANCED: "balanced",
        QualityMode.QUALITY: "quality", QualityMode.CINEMA: "cinema",
    }
    mode = quality_map.get(project.config.quality, "quality")
    default_models = {
        "cinema": "cinematic-studio-3", "quality": "cinematic-studio-3",
        "balanced": "fast-motion-2", "budget": "draft-1",
    }
    if available_models:
        for m in available_models:
            tier = m.get("quality_tier", "balanced")
            if tier not in default_models or tier == "budget":
                default_models[tier] = m.get("model_id", m.get("id", ""))

    for shot in project.shots:
        if shot.model_id:
            continue
        prefs = MODEL_PREFERENCES.get(shot.shot_type, ["balanced"])
        if mode == "budget":
            shot.model_id = default_models.get("budget", "draft-1")
        elif mode == "cinema":
            shot.model_id = default_models.get("cinema", "cinematic-studio-3")
        else:
            for pref in prefs:
                if pref in default_models:
                    shot.model_id = default_models[pref]
                    break
            if not shot.model_id:
                shot.model_id = default_models.get(mode, "fast-motion-2")
    return project


def build_dependency_graph(project: ProductionProject) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = {}
    sorted_shots = sorted(project.shots, key=lambda s: s.sequence)
    for i, shot in enumerate(sorted_shots):
        shot_deps = list(shot.dependency_ids) + list(shot.reference_shot_ids)
        if i > 0 and sorted_shots[i - 1].scene_id == shot.scene_id:
            prev_id = sorted_shots[i - 1].id
            if prev_id not in shot_deps:
                shot_deps.append(prev_id)
        deps[shot.id] = list(set(shot_deps))
    return deps


def get_generation_batches(project: ProductionProject) -> list[list[str]]:
    deps = build_dependency_graph(project)
    remaining = {s.id for s in project.shots if s.status in (
        ShotStatus.PLANNED, ShotStatus.PROMPTING, ShotStatus.QUEUED, ShotStatus.REJECTED)}
    completed = {s.id for s in project.shots if s.status in (ShotStatus.APPROVED, ShotStatus.SKIPPED)}
    batches: list[list[str]] = []
    while remaining:
        ready = [sid for sid in remaining
                 if all(d in completed or d not in remaining for d in deps.get(sid, []))]
        if not ready:
            shot_map = {s.id: s for s in project.shots}
            ready = [sorted(remaining, key=lambda sid: shot_map.get(sid, Shot()).sequence)[0]]
        batches.append(ready)
        for sid in ready:
            remaining.discard(sid)
            completed.add(sid)
    return batches


def get_smart_generation_order(project: ProductionProject) -> list[str]:
    return [s.id for s in sorted(project.shots, key=lambda s: (-s.importance, s.sequence))
            if s.status not in (ShotStatus.APPROVED, ShotStatus.SKIPPED)]


def get_upgrade_candidates(project: ProductionProject) -> list[str]:
    return [s.id for s in sorted(project.shots, key=lambda s: -s.importance)
            if s.status == ShotStatus.APPROVED and s.importance >= 0.7
            and s.versions and s.versions[-1].model_used not in ("cinematic-studio-3",)]
