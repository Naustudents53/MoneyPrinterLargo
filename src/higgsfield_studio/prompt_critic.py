"""Prompt quality critic — reviews and optimizes video generation prompts."""
from __future__ import annotations
import json
import logging
from .models import ProductionProject, Shot
from .script_engine import _parse_json_from_llm

log = logging.getLogger(__name__)


def critique_prompts(project: ProductionProject) -> ProductionProject:
    """Review and optimize all shot prompts."""
    from llm_provider import generate_text

    batch_size = 8
    sorted_shots = sorted(project.shots, key=lambda s: s.sequence)

    for i in range(0, len(sorted_shots), batch_size):
        batch = sorted_shots[i:i + batch_size]
        prompts_to_review = []
        for shot in batch:
            if not shot.prompt:
                continue
            prompts_to_review.append({
                "shot_id": shot.id,
                "shot_type": shot.shot_type.value if hasattr(shot.shot_type, 'value') else str(shot.shot_type),
                "duration": shot.duration_sec,
                "prompt": shot.prompt[:500],
                "negative_prompt": shot.negative_prompt[:200] if shot.negative_prompt else "",
            })

        if not prompts_to_review:
            continue

        critic_prompt = f"""You are a prompt quality critic for AI video generation.

Review these prompts and score each one. Detect:
- Vagueness (unclear subjects/actions)
- Contradictions (conflicting instructions)
- Too many subjects (more than 2 main subjects)
- Impossible movements (physically implausible)
- Incoherent camera (conflicting camera instructions)
- Contradictory lighting
- Overly complex actions (too much happening)
- Prompt too long (>300 words) or too short (<30 words)
- Redundant instructions
- Generic filler ("cinematic 8k masterpiece")

PROMPTS TO REVIEW:
{json.dumps(prompts_to_review, indent=2, ensure_ascii=False)[:4000]}

For each prompt, return:
- "shot_id": the shot id
- "quality_score": 0-100
- "issues": array of detected issues (empty if clean)
- "optimized_prompt": improved version (or original if score >= 85)

Return a JSON array. No other text."""

        response = generate_text(critic_prompt, temperature=0.3)
        parsed = _parse_json_from_llm(response)

        if parsed and isinstance(parsed, list):
            result_map = {item["shot_id"]: item for item in parsed if isinstance(item, dict) and "shot_id" in item}
            for shot in batch:
                result = result_map.get(shot.id)
                if result:
                    shot.prompt_quality_score = float(result.get("quality_score", 50))
                    optimized = result.get("optimized_prompt", "")
                    if optimized and shot.prompt_quality_score < 85:
                        shot.optimized_prompt = optimized
                    else:
                        shot.optimized_prompt = shot.prompt

    # Shots without optimized prompts keep their original
    for shot in project.shots:
        if not shot.optimized_prompt:
            shot.optimized_prompt = shot.prompt

    return project


def critique_single_prompt(prompt: str, shot_type: str = "", duration: float = 5.0) -> dict:
    """Critique a single prompt, returning score and optimized version."""
    from llm_provider import generate_text

    critic_prompt = f"""Rate this AI video generation prompt on a 0-100 scale.
Check for: vagueness, contradictions, impossible physics, keyword spam, redundancy.

PROMPT: {prompt}
SHOT TYPE: {shot_type}
DURATION: {duration}s

Return JSON: {{"quality_score": N, "issues": [...], "optimized_prompt": "..."}}"""

    response = generate_text(critic_prompt, temperature=0.3)
    parsed = _parse_json_from_llm(response)
    if parsed and isinstance(parsed, dict):
        return parsed
    return {"quality_score": 50, "issues": ["Could not parse critique"], "optimized_prompt": prompt}
