"""Quality control for generated video shots."""
from __future__ import annotations
import logging
from .models import (
    ProductionProject, Shot, ShotStatus, QCResult, ShotVersion,
    RetryStrategy, _now,
)

log = logging.getLogger(__name__)


def evaluate_shot(project: ProductionProject, shot: Shot,
                  auto_approve_threshold: float | None = None) -> QCResult:
    """Evaluate a generated shot's quality.

    In the current implementation, QC scoring is prompt-based (heuristic).
    Future versions can integrate CLIP scores, frame analysis, etc.
    """
    threshold = auto_approve_threshold or project.config.quality.value
    # Map quality mode to threshold
    threshold_map = {"budget": 50, "balanced": 65, "quality": 75, "cinema": 85}
    if isinstance(threshold, str):
        threshold = threshold_map.get(threshold, 75)

    # Heuristic QC based on generation metadata
    qc = QCResult()

    latest_version = shot.versions[-1] if shot.versions else None
    if not latest_version:
        qc.overall_score = 0
        qc.issues = ["No generated version available"]
        return qc

    # Score based on available signals
    scores = []

    # Prompt alignment: did we use the optimized prompt?
    if latest_version.prompt_used:
        if latest_version.prompt_used == (shot.optimized_prompt or shot.prompt):
            qc.prompt_alignment = 85
        else:
            qc.prompt_alignment = 60
        scores.append(qc.prompt_alignment)

    # If we have no real video analysis, use heuristic scores
    # In production, this would analyze actual frames
    if latest_version.file_path or latest_version.provider_job_id.startswith("dry-run"):
        qc.visual_quality = 80
        qc.motion_quality = 75
        qc.composition_quality = 78
        qc.cinematic_score = 76
        qc.artifact_score = 85  # Higher = fewer artifacts
        scores.extend([qc.visual_quality, qc.motion_quality,
                       qc.composition_quality, qc.cinematic_score, qc.artifact_score])

    # Continuity checks
    from .continuity import check_continuity
    issues = check_continuity(project, shot)
    if issues:
        qc.identity_consistency = 60
        qc.temporal_consistency = 60
        qc.issues.extend(issues)
    else:
        qc.identity_consistency = 85
        qc.temporal_consistency = 85
    scores.extend([qc.identity_consistency, qc.temporal_consistency])

    qc.overall_score = sum(scores) / len(scores) if scores else 0
    qc.passed = qc.overall_score >= threshold

    if latest_version:
        latest_version.qc = qc

    # Update shot status
    if qc.passed:
        shot.status = ShotStatus.APPROVED
    else:
        shot.status = ShotStatus.REJECTED

    return qc


def select_retry_strategy(shot: Shot, qc: QCResult) -> RetryStrategy:
    """Select the best retry strategy based on QC results."""
    if shot.regeneration_count == 0:
        return RetryStrategy.SAME

    if qc.prompt_alignment < 60:
        return RetryStrategy.REWRITE

    if qc.motion_quality < 50:
        return RetryStrategy.SIMPLIFY

    if shot.regeneration_count >= 2:
        return RetryStrategy.DIFFERENT_MODEL

    return RetryStrategy.TEMPERATURE


def run_qc_pass(project: ProductionProject) -> dict:
    """Run QC on all shots that need it."""
    results = {"passed": 0, "failed": 0, "skipped": 0}

    for shot in project.shots:
        if shot.status not in (ShotStatus.QC_PENDING, ShotStatus.GENERATING):
            if shot.status == ShotStatus.APPROVED:
                results["passed"] += 1
            elif shot.status == ShotStatus.FAILED:
                results["failed"] += 1
            else:
                results["skipped"] += 1
            continue

        qc = evaluate_shot(project, shot)
        if qc.passed:
            results["passed"] += 1
        else:
            results["failed"] += 1

    return results


def final_quality_gate(project: ProductionProject) -> dict:
    """Final quality gate before declaring production complete."""
    issues = []

    # Check all narration exists
    for block in project.narration_blocks:
        if not block.audio_path and not project.config.dry_run:
            issues.append(f"Missing narration audio for block {block.id}")

    # Check all required shots exist
    for shot in project.shots:
        if shot.status == ShotStatus.SKIPPED:
            continue
        if shot.status != ShotStatus.APPROVED:
            issues.append(f"Shot {shot.id} not approved (status: {shot.status.value})")
        if not shot.versions and not project.config.dry_run:
            issues.append(f"Shot {shot.id} has no generated versions")

    # Check output files
    if not project.config.dry_run:
        import os
        if project.outputs.master_video and not os.path.exists(project.outputs.master_video):
            issues.append("Master video file missing")
        if project.outputs.captions_srt and not os.path.exists(project.outputs.captions_srt):
            issues.append("SRT captions file missing")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "total_shots": len(project.shots),
        "approved_shots": project.completed_shots(),
        "failed_shots": project.failed_shots(),
    }
