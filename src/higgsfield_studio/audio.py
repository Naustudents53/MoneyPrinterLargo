"""Audio production — TTS narration."""
from __future__ import annotations
import logging
import os
from pathlib import Path
from .models import ProductionProject, AudioTrack, AudioType, NarrationBlock

log = logging.getLogger(__name__)


def produce_audio(project: ProductionProject) -> ProductionProject:
    import sys
    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
    audio_dir = Path(root) / ".mp" / "higgsfield" / "audio" / project.id
    audio_dir.mkdir(parents=True, exist_ok=True)
    for block in project.narration_blocks:
        if block.audio_path and os.path.exists(block.audio_path):
            continue
        output_path = audio_dir / f"narration_{block.id}.wav"
        try:
            _synthesize_block(block, output_path, project)
            block.audio_path = str(output_path)
            dur = _get_audio_duration(output_path)
            if dur:
                block.actual_duration_sec = dur
        except Exception as e:
            log.error("TTS failed for block %s: %s", block.id, e)
    from .script_engine import recalculate_timing
    project = recalculate_timing(project)
    tracks: list[AudioTrack] = []
    for block in project.narration_blocks:
        if block.audio_path:
            tracks.append(AudioTrack(type=AudioType.NARRATION, start_sec=block.start_sec,
                                     end_sec=block.end_sec, volume=1.0, source_path=block.audio_path))
    project.audio_tracks = tracks
    return project


def _synthesize_block(block: NarrationBlock, output_path: Path, project: ProductionProject):
    import asyncio, edge_tts
    voice = project.config.narrator_voice or _default_voice(project.config.language)
    rate = "-5%"
    if "slow" in (block.delivery or "").lower():
        rate = "-12%"
    elif "fast" in (block.delivery or "").lower() or "urgent" in (block.delivery or "").lower():
        rate = "+5%"

    async def _synth():
        comm = edge_tts.Communicate(block.text, voice, rate=rate, pitch="-10Hz")
        await comm.save(str(output_path))

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_synth())
    finally:
        loop.close()


def _default_voice(language: str) -> str:
    return {"es": "es-ES-AlvaroNeural", "en": "en-US-GuyNeural", "pt": "pt-BR-AntonioNeural",
            "fr": "fr-FR-HenriNeural", "de": "de-DE-ConradNeural", "it": "it-IT-DiegoNeural",
            }.get(language[:2], "en-US-GuyNeural")


def _get_audio_duration(path: Path) -> float | None:
    try:
        import subprocess
        r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    try:
        return path.stat().st_size / (24000 * 2)
    except Exception:
        return None
