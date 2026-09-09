"""Production manifest generator."""
from __future__ import annotations
import json
import os
import sys
from .models import ProductionProject


def generate_manifest(project: ProductionProject) -> ProductionProject:
    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
    path = os.path.join(root, ".mp", "higgsfield", "output", project.id, "production_manifest.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    manifest = {
        "version": "1.0",
        "project": {
            "id": project.id, "version": project.version,
            "title": project.config.title, "topic": project.config.topic,
            "genre": project.config.genre, "language": project.config.language,
            "target_duration_min": project.config.target_duration_min,
            "aspect_ratio": project.config.aspect_ratio, "resolution": project.config.resolution,
            "quality": project.config.quality.value if hasattr(project.config.quality, 'value') else str(project.config.quality),
            "provider": project.config.provider,
            "created_at": project.created_at, "updated_at": project.updated_at,
        },
        "script": {
            "concept": project.concept[:500] if project.concept else "",
            "total_blocks": len(project.narration_blocks),
            "total_words": sum(b.word_count for b in project.narration_blocks),
            "estimated_duration_sec": project.estimated_duration_sec(),
        },
        "chapters": [{"title": ch.title, "start": ch.start_sec, "end": ch.end_sec} for ch in project.chapters],
        "scenes": len(project.scenes),
        "shots": {"total": len(project.shots), "approved": project.completed_shots(), "failed": project.failed_shots()},
        "cost": {"total_estimated": round(project.total_estimated_cost(), 4),
                 "total_actual": round(project.total_actual_cost(), 4), "budget_limit": project.config.budget_limit},
        "outputs": {"master_video": project.outputs.master_video, "preview_video": project.outputs.preview_video,
                     "thumbnail": project.outputs.thumbnail, "captions_srt": project.outputs.captions_srt,
                     "captions_vtt": project.outputs.captions_vtt, "metadata": project.outputs.metadata_json},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    project.outputs.manifest_json = path
    return project
