"""Visual rhythm engine — analyzes and improves shot variety."""
from __future__ import annotations
import logging
from collections import Counter
from .models import ProductionProject, Shot, ShotType, RhythmMetrics

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_SAME_TYPE = 3
MAX_CONSECUTIVE_SAME_CAMERA = 4


def analyze_rhythm(project: ProductionProject) -> ProductionProject:
    """Analyze visual rhythm and produce variety metrics."""
    shots = sorted(project.shots, key=lambda s: s.sequence)
    if not shots:
        return project

    n = len(shots)
    types = Counter(s.shot_type for s in shots)
    cameras = Counter(s.camera for s in shots if s.camera)
    compositions = Counter(s.composition for s in shots if s.composition)
    locations = Counter(s.environment for s in shots if s.environment)

    # Variety = 1 - (max_frequency / total)
    type_variety = 1 - (max(types.values()) / n) if types else 0
    cam_variety = 1 - (max(cameras.values()) / n) if cameras else 0.5
    comp_variety = 1 - (max(compositions.values()) / n) if compositions else 0.5
    loc_variety = 1 - (max(locations.values()) / n) if locations else 0.5

    # Motion variety: check for consecutive similar movements
    movements = [s.movement or s.camera or "" for s in shots]
    motion_runs = _max_consecutive_same(movements)
    motion_variety = max(0, 1 - (motion_runs / max(5, n / 3)))

    project.rhythm = RhythmMetrics(
        shot_variety=round(type_variety * 100, 1),
        camera_variety=round(cam_variety * 100, 1),
        composition_variety=round(comp_variety * 100, 1),
        motion_variety=round(motion_variety * 100, 1),
        location_variety=round(loc_variety * 100, 1),
    )

    return project


def get_rhythm_warnings(project: ProductionProject) -> list[str]:
    """Get warnings about monotonous shot patterns."""
    warnings = []
    shots = sorted(project.shots, key=lambda s: s.sequence)
    if not shots:
        return warnings

    # Check consecutive same shot types
    run = 1
    for i in range(1, len(shots)):
        if shots[i].shot_type == shots[i-1].shot_type:
            run += 1
            if run > MAX_CONSECUTIVE_SAME_TYPE:
                warnings.append(
                    f"Shots {shots[i-run+1].sequence}-{shots[i].sequence}: "
                    f"{run} consecutive {shots[i].shot_type.value} shots"
                )
        else:
            run = 1

    # Check metrics thresholds
    r = project.rhythm
    if r.shot_variety < 30:
        warnings.append(f"Low shot type variety ({r.shot_variety}%)")
    if r.camera_variety < 25:
        warnings.append(f"Low camera variety ({r.camera_variety}%)")
    if r.motion_variety < 25:
        warnings.append(f"Low motion variety ({r.motion_variety}%)")

    return warnings


def _max_consecutive_same(items: list[str]) -> int:
    if not items:
        return 0
    max_run = 1
    run = 1
    for i in range(1, len(items)):
        if items[i] == items[i-1] and items[i]:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    return max_run
