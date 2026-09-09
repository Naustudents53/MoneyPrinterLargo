"""YouTube metadata generation."""
from __future__ import annotations
import json
import logging
import os
import sys
from .models import ProductionProject
from .script_engine import _parse_json_from_llm
from .timeline import format_timecode

log = logging.getLogger(__name__)


def generate_metadata(project: ProductionProject) -> ProductionProject:
    from llm_provider import generate_text
    script_preview = project.script_raw[:1500] if project.script_raw else project.config.topic
    prompt = f"""Generate YouTube metadata for this video.
TOPIC: {project.config.topic}
TITLE: {project.config.title}
GENRE: {project.config.genre}
LANGUAGE: {project.config.language}
DURATION: {project.estimated_duration_sec() / 60:.0f} min

SCRIPT: {script_preview}

Return JSON with: "title" (max 100 chars), "description" (200-400 words), "tags" (15-25), "seo_keywords" (5-10).
Write in {project.config.language}. No other text."""

    response = generate_text(prompt, temperature=0.7)
    parsed = _parse_json_from_llm(response)
    metadata = parsed if parsed and isinstance(parsed, dict) else {
        "title": project.config.title or project.config.topic,
        "description": project.script_raw[:500] if project.script_raw else "",
        "tags": [], "seo_keywords": []}

    if project.chapters:
        chapters_text = "\n\nChapters:\n"
        for ch in project.chapters:
            chapters_text += f"{format_timecode(ch.start_sec)} {ch.title}\n"
        metadata["description"] = metadata.get("description", "") + chapters_text

    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
    meta_path = os.path.join(root, ".mp", "higgsfield", "output", project.id, "metadata.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    project.outputs.metadata_json = meta_path
    return project
