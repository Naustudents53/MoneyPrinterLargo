"""Timeline management for production projects."""
from __future__ import annotations
import logging
from .models import ProductionProject, Shot, Scene, AudioTrack, AudioType

log = logging.getLogger(__name__)


def build_timeline(project: ProductionProject) -> ProductionProject:
    """Build the final timeline by synchronizing shots with narration."""
    if not project.narration_blocks:
        return project

    # Map scenes to their narration timing
    block_map = {b.id: b for b in project.narration_blocks}
    shot_map = {s.id: s for s in project.shots}

    for scene in project.scenes:
        # Get the narration blocks for this scene
        scene_blocks = [block_map[bid] for bid in scene.narration_ids if bid in block_map]
        if not scene_blocks:
            continue

        scene.timecode_start = min(b.start_sec for b in scene_blocks)
        scene.timecode_end = max(b.end_sec for b in scene_blocks)
        scene.duration_sec = scene.timecode_end - scene.timecode_start

        # Distribute shot durations within the scene
        scene_shots = [shot_map[sid] for sid in scene.shot_ids if sid in shot_map]
        if not scene_shots:
            continue

        total_shot_dur = sum(s.duration_sec for s in scene_shots)
        if total_shot_dur <= 0:
            continue

        # Scale shots to fill scene duration
        scale = scene.duration_sec / total_shot_dur
        current_time = scene.timecode_start
        for shot in scene_shots:
            shot.duration_sec = shot.duration_sec * scale
            current_time += shot.duration_sec

    # Build audio tracks from narration blocks
    audio_tracks: list[AudioTrack] = []
    for block in project.narration_blocks:
        if block.audio_path:
            audio_tracks.append(AudioTrack(
                type=AudioType.NARRATION,
                start_sec=block.start_sec,
                end_sec=block.end_sec,
                volume=1.0,
                source_path=block.audio_path,
            ))

    # Add existing audio tracks that aren't narration
    for track in project.audio_tracks:
        if track.type != AudioType.NARRATION:
            audio_tracks.append(track)

    project.audio_tracks = audio_tracks
    return project


def recalculate_from_audio(project: ProductionProject) -> ProductionProject:
    """Recalculate timeline based on actual audio durations."""
    from .script_engine import recalculate_timing
    project = recalculate_timing(project)
    return build_timeline(project)


def get_timeline_summary(project: ProductionProject) -> list[dict]:
    """Get a timeline summary for display."""
    entries = []
    for scene in sorted(project.scenes, key=lambda s: s.timecode_start):
        shot_map = {s.id: s for s in project.shots}
        scene_shots = [shot_map[sid] for sid in scene.shot_ids if sid in shot_map]
        entries.append({
            "type": "scene",
            "id": scene.id,
            "start": scene.timecode_start,
            "end": scene.timecode_end,
            "duration": scene.duration_sec,
            "visual_goal": scene.visual_goal,
            "shot_count": len(scene_shots),
            "chapter_id": scene.chapter_id,
        })
    return entries


def format_timecode(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
