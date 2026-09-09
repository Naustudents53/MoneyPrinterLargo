"""Cinematic long-form script engine."""
from __future__ import annotations
import json
import logging
import re
from .models import (
    ProductionProject, NarrationBlock, Chapter, NarrativeElement,
    ProjectConfig, GENRE_STYLES,
)

log = logging.getLogger(__name__)

WPM = {"es": 140, "en": 150, "pt": 140, "fr": 145, "de": 135, "it": 145}


def _wpm(lang: str) -> int:
    return WPM.get(lang[:2], 145)


def _estimate_duration(word_count: int, lang: str) -> float:
    return (word_count / _wpm(lang)) * 60


def _parse_json_from_llm(text: str) -> dict | list | None:
    """Extract JSON from LLM response that may contain markdown fences."""
    # Try direct parse
    text = text.strip()
    for attempt in [text, re.sub(r'^```(?:json)?\s*', '', text).rstrip('`').strip()]:
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    # Try to find JSON block
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try to find array or object
    for pattern in [r'(\[[\s\S]*\])', r'(\{[\s\S]*\})']:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _build_script_prompt(config: ProjectConfig, concept: str = "", research: str = "") -> str:
    target_words = int(config.target_duration_min * _wpm(config.language))
    genre_style = GENRE_STYLES.get(config.genre, GENRE_STYLES["documentary"])

    lang_instruction = {
        "es": "Write the narration in Spanish.",
        "en": "Write the narration in English.",
        "pt": "Write the narration in Portuguese.",
        "fr": "Write the narration in French.",
    }.get(config.language[:2], f"Write the narration in language code: {config.language}.")

    prompt = f"""You are a world-class documentary screenwriter and narrative architect.

TASK: Write a complete narration script for a {config.target_duration_min:.0f}-minute cinematic video.

TOPIC: {config.topic}
{"CONCEPT: " + concept if concept else ""}
{"RESEARCH NOTES: " + research[:2000] if research else ""}
GENRE: {config.genre}
VISUAL TONE: {genre_style.get('visual_tone', '')}
TARGET WORD COUNT: {target_words} words (±10%)
{lang_instruction}

NARRATIVE STRUCTURE — produce blocks in this order:
1. HOOK — a provocative opening that creates immediate curiosity (15-25 words)
2. COLD_OPEN — a vivid scene or moment that drops the viewer into the story (80-120 words)
3. SETUP — establish the context, stakes, and world (150-250 words)
4. PREMISE — the central question or thesis (80-120 words)
5. ESCALATION — build complexity, introduce layers (200-400 words)
6. EXPOSITION — key information delivery with narrative momentum (200-400 words)
7. DISCOVERY — new information that shifts understanding (150-300 words)
8. CONFLICT — tension, contradiction, or challenge (150-300 words)
9. REVEAL — the pivotal insight or turning point (100-200 words)
10. CLIMAX — the peak of narrative tension (100-200 words)
11. RESOLUTION — how things settle or transform (100-200 words)
12. TAKEAWAY — final reflection that lingers (50-100 words)

For each narration block, provide:
- "element": the narrative element name (hook, cold_open, setup, etc.)
- "text": the narration text
- "emotion": the emotional tone (tense, wonder, somber, urgent, contemplative, etc.)
- "delivery": narration delivery style (slow/confidential, energetic, measured, whispered, etc.)
- "visual_intent": brief description of what should be on screen

RULES:
- Write for the EAR, not the eye. Short sentences. Rhythm matters.
- Vary sentence length for pacing. Short. Then longer, building.
- Use concrete imagery, not abstractions.
- Create genuine curiosity gaps.
- Each block should feel like it NEEDS the next one.
- No filler. No padding. Every sentence earns its place.
- The hook must be irresistible in under 8 seconds of speech.

Return ONLY a JSON array of objects. No other text."""

    return prompt


def _build_concept_prompt(config: ProjectConfig) -> str:
    return f"""You are a creative director for cinematic documentaries.

TOPIC: {config.topic}
GENRE: {config.genre}
DURATION: {config.target_duration_min:.0f} minutes
LANGUAGE: {config.language}

Create a creative concept for this production. Include:
1. THESIS: The central argument or question (1-2 sentences)
2. ANGLE: The unique perspective or approach (1-2 sentences)
3. EMOTIONAL_ARC: The emotional journey for the viewer (3-4 key beats)
4. VISUAL_CONCEPT: The overarching visual approach (2-3 sentences)
5. HOOK_CONCEPT: What makes someone click and stay (1 sentence)
6. TARGET_AUDIENCE: Who this is for (1 sentence)

Return as a JSON object with these keys. No other text."""


def _build_research_prompt(topic: str, depth: str = "light") -> str:
    if depth == "deep":
        return f"""Research the following topic thoroughly. Provide:
1. KEY_FACTS: 10-15 verified facts with specifics (dates, numbers, names)
2. TIMELINE: Major chronological events
3. KEY_FIGURES: Important people involved
4. CONTROVERSIES: Debated aspects or mysteries
5. LESSER_KNOWN: Surprising or little-known details
6. SOURCES: Types of sources this information comes from

TOPIC: {topic}

Return as a JSON object. Focus on accuracy and specificity."""
    else:
        return f"""Provide a brief research summary for this topic:
TOPIC: {topic}

Include:
1. KEY_FACTS: 5-8 essential facts
2. KEY_FIGURES: Main people/entities involved
3. HOOK_ANGLES: 3 angles that create curiosity

Return as a JSON object."""


def generate_concept(project: ProductionProject) -> ProductionProject:
    """Generate creative concept for the production."""
    from llm_provider import generate_text
    prompt = _build_concept_prompt(project.config)
    response = generate_text(prompt, temperature=0.8)
    parsed = _parse_json_from_llm(response)
    if parsed and isinstance(parsed, dict):
        parts = []
        for key in ["thesis", "angle", "emotional_arc", "visual_concept", "hook_concept", "target_audience",
                     "THESIS", "ANGLE", "EMOTIONAL_ARC", "VISUAL_CONCEPT", "HOOK_CONCEPT", "TARGET_AUDIENCE"]:
            val = parsed.get(key)
            if val:
                label = key.upper().replace("_", " ")
                if isinstance(val, list):
                    val = " → ".join(str(v) for v in val)
                parts.append(f"{label}: {val}")
        project.concept = "\n".join(parts) if parts else response
    else:
        project.concept = response
    return project


def generate_research(project: ProductionProject) -> ProductionProject:
    """Generate research notes for the topic."""
    if project.config.research_mode == "none":
        return project
    from llm_provider import generate_text
    prompt = _build_research_prompt(project.config.topic, project.config.research_mode)
    response = generate_text(prompt, temperature=0.3)
    parsed = _parse_json_from_llm(response)
    if parsed and isinstance(parsed, dict):
        parts = []
        for key, val in parsed.items():
            if isinstance(val, list):
                items = "\n".join(f"  - {v}" for v in val)
                parts.append(f"{key.upper()}:\n{items}")
            else:
                parts.append(f"{key.upper()}: {val}")
        project.research = "\n\n".join(parts)
    else:
        project.research = response
    return project


def generate_script(project: ProductionProject) -> ProductionProject:
    """Generate the full narration script."""
    from llm_provider import generate_text
    prompt = _build_script_prompt(project.config, project.concept, project.research)
    response = generate_text(prompt, temperature=0.7)
    parsed = _parse_json_from_llm(response)

    blocks: list[NarrationBlock] = []
    element_map = {e.value: e for e in NarrativeElement}

    if parsed and isinstance(parsed, list):
        cumulative_sec = 0.0
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            word_count = len(text.split())
            duration = _estimate_duration(word_count, project.config.language)
            elem_str = item.get("element", "exposition").lower().strip()
            element = element_map.get(elem_str, NarrativeElement.EXPOSITION)

            block = NarrationBlock(
                sequence=i,
                text=text,
                narrative_element=element,
                emotion=item.get("emotion", "neutral"),
                delivery=item.get("delivery", "normal"),
                visual_intent=item.get("visual_intent", ""),
                word_count=word_count,
                estimated_duration_sec=duration,
                start_sec=cumulative_sec,
                end_sec=cumulative_sec + duration,
            )
            blocks.append(block)
            cumulative_sec += duration
    else:
        # Fallback: treat entire response as a single block
        log.warning("Could not parse structured script, using raw text")
        text = response
        word_count = len(text.split())
        duration = _estimate_duration(word_count, project.config.language)
        blocks.append(NarrationBlock(
            sequence=0, text=text, word_count=word_count,
            estimated_duration_sec=duration, start_sec=0, end_sec=duration,
        ))

    project.narration_blocks = blocks
    project.script_raw = "\n\n".join(b.text for b in blocks)

    # Generate chapters from narrative structure
    project.chapters = _generate_chapters(blocks)

    return project


def _generate_chapters(blocks: list[NarrationBlock]) -> list[Chapter]:
    """Group narration blocks into chapters."""
    chapter_groups = [
        ("Introduction", [NarrativeElement.HOOK, NarrativeElement.COLD_OPEN, NarrativeElement.SETUP]),
        ("The Question", [NarrativeElement.PREMISE, NarrativeElement.ESCALATION]),
        ("Investigation", [NarrativeElement.EXPOSITION, NarrativeElement.DISCOVERY]),
        ("The Truth", [NarrativeElement.CONFLICT, NarrativeElement.REVEAL]),
        ("Conclusion", [NarrativeElement.CLIMAX, NarrativeElement.RESOLUTION, NarrativeElement.TAKEAWAY]),
    ]

    chapters: list[Chapter] = []
    used_blocks: set[str] = set()

    for seq, (title, elements) in enumerate(chapter_groups):
        chapter_blocks = [b for b in blocks if b.narrative_element in elements and b.id not in used_blocks]
        if not chapter_blocks:
            continue
        for b in chapter_blocks:
            used_blocks.add(b.id)
        chapters.append(Chapter(
            sequence=seq,
            title=title,
            start_sec=min(b.start_sec for b in chapter_blocks),
            end_sec=max(b.end_sec for b in chapter_blocks),
            narration_ids=[b.id for b in chapter_blocks],
            hook=chapter_blocks[0].text[:100] + "..." if chapter_blocks[0].text else "",
        ))

    # Any remaining blocks go into the last chapter
    remaining = [b for b in blocks if b.id not in used_blocks]
    if remaining:
        if chapters:
            last = chapters[-1]
            last.narration_ids.extend(b.id for b in remaining)
            last.end_sec = max(last.end_sec, max(b.end_sec for b in remaining))
        else:
            chapters.append(Chapter(
                sequence=0, title="Content",
                start_sec=remaining[0].start_sec,
                end_sec=remaining[-1].end_sec,
                narration_ids=[b.id for b in remaining],
            ))

    return chapters


def recalculate_timing(project: ProductionProject) -> ProductionProject:
    """Recalculate all timings based on actual audio durations where available."""
    cumulative = 0.0
    for block in project.narration_blocks:
        block.start_sec = cumulative
        duration = block.actual_duration_sec or block.estimated_duration_sec
        block.end_sec = cumulative + duration
        cumulative += duration

    # Update chapter timings
    block_map = {b.id: b for b in project.narration_blocks}
    for chapter in project.chapters:
        ch_blocks = [block_map[bid] for bid in chapter.narration_ids if bid in block_map]
        if ch_blocks:
            chapter.start_sec = min(b.start_sec for b in ch_blocks)
            chapter.end_sec = max(b.end_sec for b in ch_blocks)

    return project
