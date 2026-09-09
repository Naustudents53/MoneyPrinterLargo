"""Final video renderer — FFmpeg-based assembly."""
from __future__ import annotations
import logging
import os
import subprocess
from pathlib import Path
from .models import ProductionProject, ShotStatus, AudioType

log = logging.getLogger(__name__)


def render_final(project: ProductionProject) -> ProductionProject:
    import sys
    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
    output_dir = Path(root) / ".mp" / "higgsfield" / "output" / project.id
    output_dir.mkdir(parents=True, exist_ok=True)

    ordered_shots = sorted([s for s in project.shots if s.status == ShotStatus.APPROVED], key=lambda s: s.sequence)
    clip_paths = []
    for shot in ordered_shots:
        if not shot.versions:
            continue
        sel = next((v for v in shot.versions if v.version == shot.selected_version), shot.versions[-1])
        if sel.file_path and os.path.exists(sel.file_path):
            clip_paths.append(sel.file_path)

    if not clip_paths:
        log.warning("No clips to render")
        project.outputs.manifest_json = str(output_dir / "production_manifest.json")
        return project

    concat_file = output_dir / "concat.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    master = output_dir / "master.mp4"
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(master)],
                        capture_output=True, timeout=3600, check=True)
    except Exception as e:
        log.error("FFmpeg concat failed: %s", e)
        project.error = f"Render failed: {e}"
        return project

    narration_tracks = [t for t in project.audio_tracks if t.type == AudioType.NARRATION and t.source_path]
    if narration_tracks:
        try:
            _mix_audio(master, narration_tracks, output_dir)
        except Exception as e:
            log.warning("Audio mix failed: %s", e)

    preview = output_dir / "preview.mp4"
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(master), "-vf", "scale=854:480",
                         "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                         "-c:a", "aac", "-b:a", "128k", str(preview)],
                        capture_output=True, timeout=600)
    except Exception:
        pass

    srt = output_dir / "captions.srt"
    vtt = output_dir / "captions.vtt"
    _gen_subtitles(project, srt, vtt)

    project.outputs.master_video = str(master)
    project.outputs.preview_video = str(preview) if preview.exists() else ""
    project.outputs.captions_srt = str(srt)
    project.outputs.captions_vtt = str(vtt)
    return project


def _mix_audio(video: Path, tracks, output_dir: Path):
    nc = output_dir / "narration_concat.txt"
    with open(nc, "w", encoding="utf-8") as f:
        for t in sorted(tracks, key=lambda t: t.start_sec):
            if os.path.exists(t.source_path):
                f.write(f"file '{t.source_path}'\n")
    combined = output_dir / "narration_combined.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(nc),
                     "-c:a", "pcm_s16le", str(combined)], capture_output=True, timeout=300)
    if combined.exists():
        mixed = output_dir / "master_mixed.mp4"
        subprocess.run(["ffmpeg", "-y", "-i", str(video), "-i", str(combined),
                         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                         "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(mixed)],
                        capture_output=True, timeout=600)
        if mixed.exists():
            mixed.replace(video)


def _gen_subtitles(project, srt_path, vtt_path):
    srt_lines = []
    for i, b in enumerate(project.narration_blocks, 1):
        srt_lines.extend([str(i), f"{_srt_t(b.start_sec)} --> {_srt_t(b.end_sec)}", b.text, ""])
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    vtt_lines = ["WEBVTT", ""]
    for b in project.narration_blocks:
        vtt_lines.extend([f"{_vtt_t(b.start_sec)} --> {_vtt_t(b.end_sec)}", b.text, ""])
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")


def _srt_t(s):
    h, m, sec, ms = int(s // 3600), int((s % 3600) // 60), int(s % 60), int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

def _vtt_t(s):
    h, m, sec, ms = int(s // 3600), int((s % 3600) // 60), int(s % 60), int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"
