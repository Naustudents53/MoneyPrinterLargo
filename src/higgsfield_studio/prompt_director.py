"""Cinematic prompt director — generates optimized video generation prompts."""
from __future__ import annotations
import json
import logging
from .models import (
    ProductionProject, Shot, Scene, VisualBible, CharacterProfile,
    LocationProfile, ShotType, GENRE_STYLES,
)
from .script_engine import _parse_json_from_llm

log = logging.getLogger(__name__)

DIRECTOR_SYSTEM = """You are simultaneously a film director, director of photography, continuity supervisor, and AI video prompt engineer.

Your job: transform shot descriptions into precise, cinematic video generation prompts.

RULES:
1. Prefer clarity over keyword spam.
2. One primary subject/action per shot.
3. Avoid impossible simultaneous movements.
4. Preserve physical plausibility.
5. Preserve spatial continuity with previous/next shots.
6. Use motivated camera movement only.
7. Use lighting consistent with location and time.
8. Use realistic human motion.
9. Avoid "cinematic 8k masterpiece" filler.
10. Use concrete visual language.
11. Define beginning and end state when useful.
12. Respect character bible (exact appearance).
13. Respect visual bible (style, camera, lighting, color).
14. Adapt complexity to what AI video models can reliably generate.
15. Keep prompts under 300 words.

Your prompts should read like a director's shot instructions, NOT a list of keywords."""


def generate_prompts(project: ProductionProject) -> ProductionProject:
    """Generate cinematic prompts for all planned shots."""
    from llm_provider import generate_text

    visual_bible_ctx = _bible_context(project.visual_bible)
    char_ctx = _character_context(project.characters)
    loc_ctx = _location_context(project.locations)

    shot_map = {s.id: s for s in project.shots}
    scene_map = {s.id: s for s in project.scenes}
    block_map = {b.id: b for b in project.narration_blocks}

    # Process shots in sequence order
    sorted_shots = sorted(project.shots, key=lambda s: s.sequence)

    # Batch shots in groups for efficiency
    batch_size = 5
    for i in range(0, len(sorted_shots), batch_size):
        batch = sorted_shots[i:i + batch_size]
        _generate_batch_prompts(
            batch, sorted_shots, scene_map, block_map,
            visual_bible_ctx, char_ctx, loc_ctx, project
        )

    return project


def _generate_batch_prompts(
    batch: list[Shot],
    all_shots: list[Shot],
    scene_map: dict,
    block_map: dict,
    visual_bible_ctx: str,
    char_ctx: str,
    loc_ctx: str,
    project: ProductionProject,
):
    from llm_provider import generate_text

    shots_info = []
    for shot in batch:
        idx = shot.sequence
        prev_shot = all_shots[idx - 1] if idx > 0 else None
        next_shot = all_shots[idx + 1] if idx < len(all_shots) - 1 else None
        scene = scene_map.get(shot.scene_id)

        # Find narration context
        narration_text = ""
        if scene:
            for nid in scene.narration_ids:
                block = block_map.get(nid)
                if block:
                    narration_text = block.text[:200]
                    break

        shots_info.append({
            "shot_id": shot.id,
            "sequence": shot.sequence,
            "shot_type": shot.shot_type.value if hasattr(shot.shot_type, 'value') else str(shot.shot_type),
            "duration": shot.duration_sec,
            "subject": shot.subject,
            "action": shot.action,
            "environment": shot.environment,
            "camera": shot.camera,
            "composition": shot.composition,
            "lighting": shot.lighting,
            "emotion": shot.emotion,
            "transition": shot.transition,
            "narration_context": narration_text,
            "previous_shot": {
                "subject": prev_shot.subject if prev_shot else "",
                "action": prev_shot.action if prev_shot else "",
                "shot_type": (prev_shot.shot_type.value if prev_shot and hasattr(prev_shot.shot_type, 'value')
                              else str(prev_shot.shot_type) if prev_shot else ""),
            },
            "next_shot_type": (next_shot.shot_type.value if next_shot and hasattr(next_shot.shot_type, 'value')
                               else str(next_shot.shot_type) if next_shot else ""),
        })

    prompt = f"""{DIRECTOR_SYSTEM}

VISUAL BIBLE:
{visual_bible_ctx}

{char_ctx}

{loc_ctx}

SHOTS TO PROMPT:
{json.dumps(shots_info, indent=2, ensure_ascii=False)[:3500]}

For EACH shot, generate:
- "shot_id": the shot id
- "prompt": a cinematic video generation prompt (150-250 words, reads like director instructions)
- "negative_prompt": what to avoid (brief, only if needed)

The prompt should flow naturally:
1. Establish the visual bible's style
2. Describe the subject and action
3. Specify camera and composition
4. Define lighting and atmosphere
5. Note continuity with previous shot
6. Describe the end state or transition intent

Return a JSON array of objects. No other text."""

    response = generate_text(prompt, temperature=0.6)
    parsed = _parse_json_from_llm(response)

    if parsed and isinstance(parsed, list):
        result_map = {}
        for item in parsed:
            if isinstance(item, dict) and "shot_id" in item:
                result_map[item["shot_id"]] = item

        for shot in batch:
            result = result_map.get(shot.id)
            if result:
                shot.prompt = result.get("prompt", "")
                shot.negative_prompt = result.get("negative_prompt", "")
            elif not shot.prompt:
                shot.prompt = _fallback_prompt(shot, project)
    else:
        for shot in batch:
            if not shot.prompt:
                shot.prompt = _fallback_prompt(shot, project)


def generate_single_prompt(shot: Shot, project: ProductionProject) -> str:
    """Generate a prompt for a single shot (for regeneration)."""
    from llm_provider import generate_text

    visual_bible_ctx = _bible_context(project.visual_bible)
    char_ctx = _character_context(project.characters)

    prev_shot = None
    next_shot = None
    for i, s in enumerate(project.shots):
        if s.id == shot.id:
            if i > 0:
                prev_shot = project.shots[i - 1]
            if i < len(project.shots) - 1:
                next_shot = project.shots[i + 1]
            break

    prompt = f"""{DIRECTOR_SYSTEM}

VISUAL BIBLE:
{visual_bible_ctx}

{char_ctx}

SHOT DETAILS:
Type: {shot.shot_type.value if hasattr(shot.shot_type, 'value') else shot.shot_type}
Duration: {shot.duration_sec}s
Subject: {shot.subject}
Action: {shot.action}
Environment: {shot.environment}
Camera: {shot.camera}
Lighting: {shot.lighting}
Emotion: {shot.emotion}
Previous shot: {prev_shot.subject + ' - ' + prev_shot.action if prev_shot else 'None'}
Next shot type: {next_shot.shot_type.value if next_shot and hasattr(next_shot.shot_type, 'value') else 'None'}

Generate ONE cinematic video generation prompt (150-250 words).
Return ONLY the prompt text, no JSON."""

    return generate_text(prompt, temperature=0.65)


def _fallback_prompt(shot: Shot, project: ProductionProject) -> str:
    """Generate a basic prompt without LLM call."""
    genre_style = GENRE_STYLES.get(project.config.genre, GENRE_STYLES["documentary"])
    parts = [genre_style.get("visual_tone", "Cinematic realism") + "."]
    if shot.subject:
        parts.append(f"{shot.subject}")
    if shot.action:
        parts.append(f"{shot.action}.")
    if shot.environment:
        parts.append(f"Setting: {shot.environment}.")
    shot_type_str = shot.shot_type.value if hasattr(shot.shot_type, 'value') else str(shot.shot_type)
    parts.append(f"{shot_type_str.replace('_', ' ').title()} shot.")
    if shot.camera:
        parts.append(f"Camera: {shot.camera}.")
    if shot.lighting:
        parts.append(f"Lighting: {shot.lighting}.")
    if shot.emotion:
        parts.append(f"Mood: {shot.emotion}.")
    return " ".join(parts)


def _bible_context(bible: VisualBible) -> str:
    parts = []
    if bible.style:
        parts.append("STYLE: " + json.dumps(bible.style, ensure_ascii=False)[:300])
    if bible.camera:
        parts.append("CAMERA: " + json.dumps(bible.camera, ensure_ascii=False)[:300])
    if bible.lighting:
        parts.append("LIGHTING: " + json.dumps(bible.lighting, ensure_ascii=False)[:200])
    if bible.color:
        parts.append("COLOR: " + json.dumps(bible.color, ensure_ascii=False)[:200])
    if bible.rules:
        parts.append("RULES: " + "; ".join(bible.rules[:5]))
    return "\n".join(parts) if parts else "Standard cinematic documentary style."


def _character_context(characters: list[CharacterProfile]) -> str:
    if not characters:
        return ""
    lines = ["CHARACTERS:"]
    for c in characters[:8]:
        desc = f"- {c.name}"
        if c.appearance:
            desc += f": {c.appearance[:100]}"
        if c.wardrobe:
            desc += f". Wardrobe: {c.wardrobe[:80]}"
        if c.continuity_rules:
            desc += f". CONTINUITY: {'; '.join(c.continuity_rules[:3])}"
        lines.append(desc)
    return "\n".join(lines)


def _location_context(locations: list[LocationProfile]) -> str:
    if not locations:
        return ""
    lines = ["LOCATIONS:"]
    for loc in locations[:8]:
        desc = f"- {loc.name}: {loc.description[:100]}"
        if loc.lighting:
            desc += f". Lighting: {loc.lighting[:60]}"
        lines.append(desc)
    return "\n".join(lines)
