"""Cost tracking and budget control."""
from __future__ import annotations
import logging
from .models import ProductionProject, Shot, CostEvent, ShotStatus, _uid, _now

log = logging.getLogger(__name__)


def estimate_production_cost(project: ProductionProject) -> dict:
    """Estimate total production cost."""
    from video_providers import get_provider
    try:
        provider = get_provider(project.config.provider, config={"dry_run": True})
    except Exception:
        provider = None

    total_estimated = 0.0
    shot_estimates = []
    cost_available = False

    for shot in project.shots:
        if shot.status in (ShotStatus.APPROVED, ShotStatus.SKIPPED):
            continue
        est = None
        if provider:
            from video_providers.base import GenerationRequest
            req = GenerationRequest(
                prompt=shot.optimized_prompt or shot.prompt or "placeholder",
                duration_sec=shot.duration_sec,
                aspect_ratio=project.config.aspect_ratio,
                resolution=project.config.resolution,
                model_id=shot.model_id,
            )
            est = provider.estimate_cost(req)
        if est is not None:
            cost_available = True
            total_estimated += est
            shot.estimated_cost = est
        shot_estimates.append({
            "shot_id": shot.id, "estimated_cost": est,
            "duration": shot.duration_sec, "model": shot.model_id,
        })

    return {
        "total_estimated": round(total_estimated, 4) if cost_available else None,
        "cost_available": cost_available,
        "shots": shot_estimates,
        "budget_limit": project.config.budget_limit,
        "budget_remaining": (
            round(project.config.budget_limit - project.total_actual_cost(), 4)
            if project.config.budget_limit else None
        ),
    }


def check_budget(project: ProductionProject, additional_cost: float = 0) -> dict:
    """Check if budget allows continued generation."""
    if project.config.budget_limit is None:
        return {"allowed": True, "reason": "no_budget_limit"}
    spent = project.total_actual_cost()
    remaining = project.config.budget_limit - spent
    if additional_cost > remaining:
        return {
            "allowed": False,
            "reason": "budget_exceeded",
            "spent": round(spent, 4),
            "remaining": round(remaining, 4),
            "requested": round(additional_cost, 4),
            "budget_limit": project.config.budget_limit,
        }
    return {"allowed": True, "remaining": round(remaining, 4)}


def record_cost(project: ProductionProject, shot_id: str, provider: str,
                model: str, estimated: float | None, actual: float | None,
                description: str = "") -> CostEvent:
    """Record a cost event."""
    event = CostEvent(
        id=_uid(), shot_id=shot_id, provider=provider, model=model,
        estimated=estimated, actual=actual, timestamp=_now(),
        description=description,
    )
    project.cost_events.append(event)
    return event


def cost_summary(project: ProductionProject) -> dict:
    """Get a cost summary for the project."""
    return {
        "total_estimated": round(project.total_estimated_cost(), 4),
        "total_actual": round(project.total_actual_cost(), 4),
        "budget_limit": project.config.budget_limit,
        "total_shots": len(project.shots),
        "completed_shots": project.completed_shots(),
        "failed_shots": project.failed_shots(),
        "events": len(project.cost_events),
    }
