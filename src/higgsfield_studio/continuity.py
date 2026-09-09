"""Continuity engine — checks visual consistency between shots."""
from __future__ import annotations
import logging
from .models import ProductionProject, Shot, ShotStatus

log = logging.getLogger(__name__)


def check_continuity(project: ProductionProject, shot: Shot) -> list[str]:
    """Check a shot for continuity issues against the production context."""
    issues = []
    idx = None
    for i, s in enumerate(project.shots):
        if s.id == shot.id:
            idx = i
            break
    if idx is None:
        return issues

    prev = project.shots[idx - 1] if idx > 0 else None
    next_s = project.shots[idx + 1] if idx < len(project.shots) - 1 else None

    # Check character consistency
    char_map = {c.name.lower(): c for c in project.characters}
    prompt_lower = (shot.optimized_prompt or shot.prompt).lower()
    for name, char in char_map.items():
        if name in prompt_lower:
            if char.wardrobe and char.wardrobe.lower() not in prompt_lower:
                pass  # Wardrobe not mentioned is OK if character bible handles it
            for rule in char.continuity_rules:
                rule_lower = rule.lower()
                # Check for obvious contradictions
                if "never" in rule_lower or "always" in rule_lower:
                    pass  # Would need semantic analysis

    # Check lighting continuity with previous shot
    if prev and prev.lighting and shot.lighting:
        if prev.lighting != shot.lighting:
            # Only flag if in same scene
            if prev.scene_id == shot.scene_id:
                if _are_contradictory(prev.lighting, shot.lighting):
                    issues.append(f"Lighting change within scene: '{prev.lighting}' → '{shot.lighting}'")

    # Check environment continuity within scene
    if prev and prev.scene_id == shot.scene_id:
        if prev.environment and shot.environment:
            if prev.environment != shot.environment:
                issues.append(f"Environment changed within scene: '{prev.environment}' → '{shot.environment}'")

    return issues


def _are_contradictory(a: str, b: str) -> bool:
    """Simple heuristic for contradictory descriptions."""
    contradictions = [
        ("day", "night"), ("bright", "dark"), ("warm", "cold"),
        ("interior", "exterior"), ("sunny", "overcast"),
    ]
    a_lower, b_lower = a.lower(), b.lower()
    for x, y in contradictions:
        if (x in a_lower and y in b_lower) or (y in a_lower and x in b_lower):
            return True
    return False


def validate_all_continuity(project: ProductionProject) -> dict[str, list[str]]:
    """Validate continuity for all shots, returning issues per shot_id."""
    all_issues: dict[str, list[str]] = {}
    for shot in project.shots:
        issues = check_continuity(project, shot)
        if issues:
            all_issues[shot.id] = issues
    return all_issues
