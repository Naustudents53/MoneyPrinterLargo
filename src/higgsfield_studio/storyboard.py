"""Storyboard and scene planning engine."""
from __future__ import annotations
import json
import logging
import math
from .models import (
    ProductionProject, Scene, Shot, ShotType, NarrationBlock,
    GENRE_STYLES, _uid,
)
from .script_engine import _parse_json_from_llm

log = logging.getLogger(__name__)

# Average shot durations by type (seconds)
SHOT_DURATION_GUIDE = {
    ShotType.ESTABLISHING: (4, 8),
    ShotType.WIDE: (3, 6),
    ShotType.MEDIUM: (3, 5),
    ShotType.CLOSE_UP: (2, 4),
    ShotType.EXTREME_CLOSE_UP: (2, 3),
    ShotType.DETAIL: (2, 4),
    ShotType.AERIAL: (4, 8),
    ShotType.B_ROLL: (3, 5),
    ShotType.TRANSITION: (1, 3),
    ShotType.HERO: (4, 7),
    ShotType.TRACKING: (3, 6),
    ShotType.PAN: (3, 5),
    ShotType.STATIC: (3, 6),
    ShotType.DOLLY: (3, 6),
    ShotType.HANDHELD: (2, 5),
    ShotType.MACRO: (2, 4),
}


def _avg_shot_duration(shot_type: ShotType) -> float:
    lo, hi = SHOT_DURATION_GUIDE.get(shot_type, (3, 5))
    return (lo + hi) / 2


def generate_storyboard(project: ProductionProject) -> ProductionProject:
    """Generate scenes and shots from the narration blocks."""
    from llm_provider import generate_text

    if not project.narration_blocks:
        log.warning("No narration blocks, cannot generate storyboard")
        return project

    # Build scene generation prompt
    blocks_summary = []
    for b in project.narration_blocks:
        blocks_summary.append({
            "id": b.id,
            "element": b.narrative_element.value if hasattr(b.narrative_element, 'value') else str(b.narrative_element),
            "start": round(b.start_sec, 1),
            "end": round(b.end_sec, 1),
            "duration": round(b.end_sec - b.start_sec, 1),
            "emotion": b.emotion,
            "visual_intent": b.visual_intent[:200] if b.visual_intent else "",
            "text_preview": b.text[:150] + "..." if len(b.text) > 150 else b.text,
        })

    genre_style = GENRE_STYLES.get(project.config.genre, GENRE_STYLES["documentary"])

    prompt = f"""You are a cinematic storyboard artist and shot planner.

PRODUCTION: {project.config.title or project.config.topic}
GENRE: {project.config.genre}
VISUAL TONE: {genre_style.get('visual_tone', '')}
CAMERA STYLE: {genre_style.get('camera_style', '')}
TOTAL DURATION: {project.estimated_duration_sec():.0f} seconds

NARRATION BLOCKS:
{json.dumps(blocks_summary, indent=2, ensure_ascii=False)[:4000]}

For each narration block, create 1-4 SCENES. Each scene should have 2-5 SHOTS.

Rules:
- Start with an ESTABLISHING shot for the first scene
- Use HERO shots for emotional peaks (reveal, climax)
- Use B_ROLL for exposition and transitions
- Vary shot types to avoid monotony
- Match shot duration to narration pacing
- Total shot durations per scene must approximately match narration duration

For each scene, provide:
- "narration_id": the narration block id
- "visual_goal": what this scene communicates visually
- "location": where this takes place
- "time_of_day": lighting context

For each shot within a scene:
- "shot_type": one of [establishing, wide, medium, close_up, detail, aerial, b_roll, transition, hero, tracking, static, dolly, handheld, macro]
- "duration": seconds (2-8)
- "subject": what/who is in frame
- "action": what happens
- "camera": camera behavior
- "composition": framing description
- "lighting": lighting description
- "emotion": emotional tone
- "transition": how to transition to next (cut, dissolve, crossfade)

Return a JSON array of scene objects, each containing a "shots" array. No other text."""

    response = generate_text(prompt, temperature=0.6)
    parsed = _parse_json_from_llm(response)

    scenes: list[Scene] = []
    shots: list[Shot] = []
    shot_seq = 0

    if parsed and isinstance(parsed, list):
        block_map = {b.id: b for b in project.narration_blocks}

        for scene_idx, scene_data in enumerate(parsed):
            if not isinstance(scene_data, dict):
                continue

            narration_id = scene_data.get("narration_id", "")
            block = block_map.get(narration_id)
            start = block.start_sec if block else scene_idx * 15
            end = block.end_sec if block else start + 15

            scene = Scene(
                chapter_id=_find_chapter_id(project, narration_id),
                sequence=scene_idx,
                timecode_start=start,
                timecode_end=end,
                duration_sec=end - start,
                narration_ids=[narration_id] if narration_id else [],
                location_id="",
                time_of_day=scene_data.get("time_of_day", ""),
                visual_goal=scene_data.get("visual_goal", ""),
                dramatic_goal=scene_data.get("dramatic_goal", ""),
                camera_goal=scene_data.get("camera_goal", ""),
            )

            scene_shots_data = scene_data.get("shots", [])
            for shot_data in scene_shots_data:
                if not isinstance(shot_data, dict):
                    continue
                shot_type_str = shot_data.get("shot_type", "medium")
                try:
                    shot_type = ShotType(shot_type_str)
                except ValueError:
                    shot_type = ShotType.MEDIUM

                shot = Shot(
                    scene_id=scene.id,
                    sequence=shot_seq,
                    duration_sec=float(shot_data.get("duration", _avg_shot_duration(shot_type))),
                    shot_type=shot_type,
                    camera=shot_data.get("camera", ""),
                    composition=shot_data.get("composition", ""),
                    subject=shot_data.get("subject", ""),
                    action=shot_data.get("action", ""),
                    environment=shot_data.get("environment", scene_data.get("location", "")),
                    lighting=shot_data.get("lighting", ""),
                    emotion=shot_data.get("emotion", ""),
                    transition=shot_data.get("transition", "cut"),
                    importance=_shot_importance(shot_type, block),
                )
                scene.shot_ids.append(shot.id)
                shots.append(shot)
                shot_seq += 1

            scenes.append(scene)
    else:
        # Fallback: create basic scenes from narration blocks
        log.warning("Could not parse storyboard, generating basic scenes")
        scenes, shots = _generate_basic_storyboard(project)

    project.scenes = scenes
    project.shots = shots
    return project


def _find_chapter_id(project: ProductionProject, narration_id: str) -> str:
    for ch in project.chapters:
        if narration_id in ch.narration_ids:
            return ch.id
    return ""


def _shot_importance(shot_type: ShotType, block: NarrationBlock | None) -> float:
    type_importance = {
        ShotType.HERO: 0.95, ShotType.ESTABLISHING: 0.8,
        ShotType.CLOSE_UP: 0.7, ShotType.AERIAL: 0.75,
        ShotType.MEDIUM: 0.5, ShotType.WIDE: 0.5,
        ShotType.B_ROLL: 0.3, ShotType.TRANSITION: 0.2,
    }
    base = type_importance.get(shot_type, 0.5)
    if block:
        from .models import NarrativeElement
        element_boost = {
            NarrativeElement.HOOK: 0.3, NarrativeElement.COLD_OPEN: 0.2,
            NarrativeElement.REVEAL: 0.25, NarrativeElement.CLIMAX: 0.3,
            NarrativeElement.TAKEAWAY: 0.15,
        }
        base = min(1.0, base + element_boost.get(block.narrative_element, 0))
    return base


def _generate_basic_storyboard(project: ProductionProject) -> tuple[list[Scene], list[Shot]]:
    """Fallback: one scene per narration block, 2-3 shots each."""
    scenes = []
    shots = []
    shot_seq = 0
    shot_types_cycle = [ShotType.ESTABLISHING, ShotType.MEDIUM, ShotType.CLOSE_UP,
                        ShotType.WIDE, ShotType.B_ROLL, ShotType.DETAIL]

    for i, block in enumerate(project.narration_blocks):
        scene = Scene(
            chapter_id=_find_chapter_id(project, block.id),
            sequence=i,
            timecode_start=block.start_sec,
            timecode_end=block.end_sec,
            duration_sec=block.end_sec - block.start_sec,
            narration_ids=[block.id],
            visual_goal=block.visual_intent,
        )

        duration = block.end_sec - block.start_sec
        n_shots = max(2, min(5, int(duration / 4)))

        for j in range(n_shots):
            st = shot_types_cycle[(shot_seq + j) % len(shot_types_cycle)]
            shot = Shot(
                scene_id=scene.id,
                sequence=shot_seq,
                duration_sec=duration / n_shots,
                shot_type=st,
                emotion=block.emotion,
                importance=_shot_importance(st, block),
            )
            scene.shot_ids.append(shot.id)
            shots.append(shot)
            shot_seq += 1

        scenes.append(scene)

    return scenes, shots
