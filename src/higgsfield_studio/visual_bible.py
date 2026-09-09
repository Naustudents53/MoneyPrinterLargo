"""Visual, character, and location bible generators."""
from __future__ import annotations
import json
import logging
from .models import (
    ProductionProject, VisualBible, CharacterProfile, LocationProfile,
    GENRE_STYLES,
)
from .script_engine import _parse_json_from_llm

log = logging.getLogger(__name__)


def generate_visual_bible(project: ProductionProject) -> ProductionProject:
    """Generate the visual bible for the production."""
    from llm_provider import generate_text

    genre_style = GENRE_STYLES.get(project.config.genre, GENRE_STYLES["documentary"])

    prompt = f"""You are a director of photography creating a Visual Bible for a cinematic production.

PRODUCTION: {project.config.title or project.config.topic}
GENRE: {project.config.genre}
STYLE REFERENCE: {json.dumps(genre_style, ensure_ascii=False)}
DURATION: {project.config.target_duration_min:.0f} minutes
ASPECT RATIO: {project.config.aspect_ratio}

Create a comprehensive Visual Bible with:

1. "style": Object with keys: visual_tone, realism_level, texture, skin_rendering, material_rendering, physics
2. "camera": Object with keys: primary_lens, secondary_lens, movement_vocabulary (array), framing_rules (array), depth_of_field
3. "lighting": Object with keys: key_approach, fill_approach, practicals, atmospheric, motivated_sources
4. "color": Object with keys: palette_description, contrast, saturation, exposure, grade_reference
5. "film_language": Object with keys: preferred_movements (array), forbidden_movements (array), transition_style, pacing
6. "rules": Array of 5-10 production rules that ALL shots must follow

Return as a JSON object. No other text."""

    response = generate_text(prompt, temperature=0.6)
    parsed = _parse_json_from_llm(response)

    if parsed and isinstance(parsed, dict):
        project.visual_bible = VisualBible(
            style=parsed.get("style", genre_style),
            camera=parsed.get("camera", {}),
            lighting=parsed.get("lighting", {}),
            color=parsed.get("color", {}),
            film_language=parsed.get("film_language", {}),
            rules=parsed.get("rules", []),
        )
    else:
        project.visual_bible = VisualBible(style=genre_style)

    return project


def generate_character_bible(project: ProductionProject) -> ProductionProject:
    """Generate character profiles from the script."""
    from llm_provider import generate_text

    script_preview = project.script_raw[:3000] if project.script_raw else project.config.topic

    prompt = f"""You are a character designer for a cinematic production.

PRODUCTION: {project.config.title or project.config.topic}
GENRE: {project.config.genre}

SCRIPT EXCERPT:
{script_preview}

Identify all characters (real or conceptual figures) that appear or are referenced in this production.
For each character, provide:
- "name": full name or designation
- "age_range": approximate age
- "appearance": overall look
- "hair": hair description
- "skin": skin tone/texture
- "body": build/posture
- "wardrobe": what they wear (era-appropriate)
- "accessories": notable items
- "personality": key traits
- "physical_traits": distinguishing features
- "continuity_rules": array of rules to maintain visual consistency

If this is a documentary about events/concepts with no specific characters, create entries for
the key real people referenced (historical figures, scientists, etc.) or for archetypal figures
used in the visual storytelling.

Return a JSON array of character objects. If no characters, return an empty array. No other text."""

    response = generate_text(prompt, temperature=0.5)
    parsed = _parse_json_from_llm(response)

    if parsed and isinstance(parsed, list):
        characters = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            characters.append(CharacterProfile(
                name=item.get("name", "Unknown"),
                age_range=item.get("age_range", ""),
                appearance=item.get("appearance", ""),
                hair=item.get("hair", ""),
                skin=item.get("skin", ""),
                body=item.get("body", ""),
                wardrobe=item.get("wardrobe", ""),
                accessories=item.get("accessories", ""),
                personality=item.get("personality", ""),
                physical_traits=item.get("physical_traits", ""),
                continuity_rules=item.get("continuity_rules", []),
            ))
        project.characters = characters

    return project


def generate_location_bible(project: ProductionProject) -> ProductionProject:
    """Generate location profiles from the script and storyboard."""
    from llm_provider import generate_text

    locations_mentioned = set()
    for scene in project.scenes:
        if scene.visual_goal:
            locations_mentioned.add(scene.visual_goal[:100])
    for block in project.narration_blocks:
        if block.visual_intent:
            locations_mentioned.add(block.visual_intent[:100])

    prompt = f"""You are a production designer creating a Location Bible.

PRODUCTION: {project.config.title or project.config.topic}
GENRE: {project.config.genre}

VISUAL REFERENCES FROM SCENES:
{chr(10).join(list(locations_mentioned)[:20])}

Identify the key locations/environments needed for this production.
For each location, provide:
- "name": location name
- "description": detailed visual description
- "architecture": structural elements
- "materials": dominant materials/textures
- "lighting": natural lighting conditions
- "weather": typical weather/atmosphere
- "time_period": era/time period
- "color_palette": array of dominant colors
- "props": array of key objects in the space
- "camera_constraints": any restrictions on camera placement

Return a JSON array. No other text."""

    response = generate_text(prompt, temperature=0.5)
    parsed = _parse_json_from_llm(response)

    if parsed and isinstance(parsed, list):
        locations = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            locations.append(LocationProfile(
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                architecture=item.get("architecture", ""),
                materials=item.get("materials", ""),
                lighting=item.get("lighting", ""),
                weather=item.get("weather", ""),
                time_period=item.get("time_period", ""),
                color_palette=item.get("color_palette", []),
                props=item.get("props", []),
                camera_constraints=item.get("camera_constraints", ""),
            ))
        project.locations = locations

    return project
