"""
MoneyPrinter Pro — job runner (subprocess driver).

Spawned by the FastAPI backend to execute long-running tasks (video
generation, upload, tweet posting) in an isolated process so progress can
be streamed line-by-line via stdout. All real work delegates to the
existing src/classes/* implementations.

Usage:
    python webapp/api/run_job.py generate --channel-id <uuid> --kind short
    python webapp/api/run_job.py generate --channel-id <uuid> --kind long  --topic "..."
    python webapp/api/run_job.py upload-last --channel-id <uuid>
    python webapp/api/run_job.py tweet --account-id <uuid>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Force ROOT_DIR to the project root regardless of CWD/sys.path layout.
import config as _mp_config  # noqa: E402
_mp_config.ROOT_DIR = str(ROOT_DIR)


def _setup_paths():
    """Replicate src/main.py's environment bootstrap."""
    # Pillow ANTIALIAS shim
    try:
        from PIL import Image as _PILImage
        if not hasattr(_PILImage, "ANTIALIAS"):
            _PILImage.ANTIALIAS = _PILImage.LANCZOS
    except Exception:
        pass

    # ffmpeg discovery
    import shutil
    if not shutil.which("ffmpeg"):
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"),
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
        ]
        for base in candidates:
            if not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                if "ffmpeg.exe" in files:
                    os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                    break
        try:
            import imageio_ffmpeg
            d = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        except ImportError:
            pass


def _select_llm_provider():
    from config import (
        get_llm_provider, get_pollinations_text_model, get_ollama_model,
    )
    from llm_provider import select_model, set_llm_provider, list_models

    provider = get_llm_provider()
    set_llm_provider(provider)

    if provider == "gemini":
        print("[runner] Using Gemini provider", flush=True)
        return

    if provider == "pollinations":
        m = get_pollinations_text_model() or "openai"
        select_model(m)
        print(f"[runner] Using Pollinations model {m}", flush=True)
        return

    # ollama
    m = get_ollama_model()
    if not m:
        try:
            models = list_models()
            if models:
                m = models[0]
        except Exception:
            pass
    if m:
        select_model(m)
        print(f"[runner] Using Ollama model {m}", flush=True)
    else:
        print("[runner] WARNING: no Ollama model selected", flush=True)


def _cleanup_after_upload(is_long: bool):
    """Remove scratch files in .mp/. Preserves long-video .mp4s so they can be
    re-uploaded or kept locally; shorts get fully wiped."""
    try:
        from utils import rem_temp_files
        rem_temp_files()
        if not is_long:
            mp_dir = os.path.join(str(ROOT_DIR), ".mp")
            if os.path.isdir(mp_dir):
                for name in os.listdir(mp_dir):
                    if name.lower().endswith(".mp4"):
                        try:
                            os.remove(os.path.join(mp_dir, name))
                        except Exception:
                            pass
            print("[runner] .mp cleaned after upload", flush=True)
        else:
            print("[runner] .mp scratch cleaned (long .mp4 preserved)", flush=True)
    except Exception as e:
        print(f"[runner] WARN: cleanup failed: {e}", flush=True)


def cmd_generate(args):
    from cache import get_accounts
    from classes.YouTube import YouTube
    from classes.Tts import TTS

    acc = next((a for a in get_accounts("youtube") if a.get("id") == args.channel_id), None)
    if not acc:
        print(f"[runner] ERROR: channel {args.channel_id} not found", flush=True)
        sys.exit(2)

    print(f"[runner] Initializing channel '{acc.get('nickname')}'", flush=True)
    youtube = YouTube(
        acc["id"],
        acc["nickname"],
        acc.get("firefox_profile", ""),
        acc.get("niche", ""),
        acc.get("language", "español"),
        image_style=acc.get("image_style", ""),
        short_voice=acc.get("short_voice", ""),
        long_voice=acc.get("long_voice", ""),
        hook_profile=acc.get("hook_profile", ""),
        voice_drama=acc.get("voice_drama", False),
    )
    tts = TTS()

    topic = args.topic or ""
    if args.kind == "long":
        if args.series_id and topic and not topic.lstrip().startswith("["):
            topic = f"[{args.series_id}] {topic}"
        print(f"[runner] Generating LONG video. Topic: {topic or '(auto)'}", flush=True)
        path = youtube.generate_long_video(tts, custom_topic=topic)
    else:
        print(f"[runner] Generating SHORT. Topic: {topic or '(auto)'}, image_mode={args.image_mode}", flush=True)
        path = youtube.generate_video(tts, custom_topic=topic, image_mode=args.image_mode)

    if not path:
        print("[runner] ERROR: generation aborted (no video produced)", flush=True)
        sys.exit(3)

    print(f"[runner] Generated: {path}", flush=True)

    if args.upload:
        print("[runner] Starting YouTube upload...", flush=True)
        ok = youtube.upload_video()
        print(f"[runner] Upload result: {ok}", flush=True)
        if not ok:
            sys.exit(4)
        _cleanup_after_upload(is_long=(args.kind == "long"))

    print("[runner] DONE", flush=True)


def cmd_upload_last(args):
    from cache import get_accounts
    from classes.YouTube import YouTube

    acc = next((a for a in get_accounts("youtube") if a.get("id") == args.channel_id), None)
    if not acc:
        print(f"[runner] ERROR: channel {args.channel_id} not found", flush=True)
        sys.exit(2)
    youtube = YouTube(
        acc["id"], acc["nickname"], acc.get("firefox_profile", ""),
        acc.get("niche", ""), acc.get("language", "español"),
        image_style=acc.get("image_style", ""),
        short_voice=acc.get("short_voice", ""),
        long_voice=acc.get("long_voice", ""),
        hook_profile=acc.get("hook_profile", ""),
        voice_drama=acc.get("voice_drama", False),
    )

    # Recover the most recent .mp4 from .mp/ (cmd_generate left it there).
    mp_dir = os.path.join(str(ROOT_DIR), ".mp")
    candidates = []
    if os.path.isdir(mp_dir):
        for name in os.listdir(mp_dir):
            if name.lower().endswith(".mp4"):
                p = os.path.join(mp_dir, name)
                try:
                    candidates.append((os.path.getmtime(p), p))
                except OSError:
                    pass
    if not candidates:
        print("[runner] ERROR: no .mp4 found in .mp/ to upload", flush=True)
        sys.exit(5)
    candidates.sort(reverse=True)
    youtube.video_path = candidates[0][1]
    youtube._is_long_video = (args.kind == "long")
    print(f"[runner] Uploading {'LONG' if args.kind == 'long' else 'SHORT'}: {youtube.video_path}", flush=True)

    ok = youtube.upload_video()
    print(f"[runner] Upload result: {ok}", flush=True)
    if not ok:
        sys.exit(4)

    _cleanup_after_upload(is_long=(args.kind == "long"))


def cmd_thumbnail(args):
    """Generate a thumbnail PNG via scripts/make_thumbnail.py (Leonardo + Pillow)."""
    script = os.path.join(str(ROOT_DIR), "scripts", "make_thumbnail.py")
    if not os.path.isfile(script):
        print(f"[runner] ERROR: thumbnail script not found at {script}", flush=True)
        sys.exit(2)

    cmd = [sys.executable, script, "--topic", args.topic, "--text", args.text, "--out", args.out]
    if args.visual:
        cmd += ["--visual", args.visual]

    print(f"[runner] Generating thumbnail → {args.out}", flush=True)
    import subprocess
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = proc.wait()
    if rc != 0:
        print(f"[runner] Thumbnail generation failed (rc={rc})", flush=True)
        sys.exit(rc)
    if not os.path.isfile(args.out):
        print(f"[runner] ERROR: expected output file missing: {args.out}", flush=True)
        sys.exit(6)
    print(f"[runner] Thumbnail saved: {args.out}", flush=True)


def cmd_tweet(args):
    from cache import get_accounts
    from classes.Twitter import Twitter

    acc = next((a for a in get_accounts("twitter") if a.get("id") == args.account_id), None)
    if not acc:
        print(f"[runner] ERROR: twitter account {args.account_id} not found", flush=True)
        sys.exit(2)
    tw = Twitter(acc["id"], acc["nickname"], acc.get("firefox_profile", ""), acc.get("topic", ""))
    tw.post()
    print("[runner] Tweet posted", flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--channel-id", required=True)
    p_gen.add_argument("--kind", choices=["short", "long"], default="short")
    p_gen.add_argument("--topic", default="")
    p_gen.add_argument("--image-mode", default="ai")
    p_gen.add_argument("--upload", action="store_true")
    p_gen.add_argument("--series-id", default="")

    p_ul = sub.add_parser("upload-last")
    p_ul.add_argument("--channel-id", required=True)
    p_ul.add_argument("--kind", choices=["short", "long"], default="short")

    p_tw = sub.add_parser("tweet")
    p_tw.add_argument("--account-id", required=True)

    p_th = sub.add_parser("thumbnail")
    p_th.add_argument("--topic", required=True)
    p_th.add_argument("--text", required=True)
    p_th.add_argument("--out", required=True)
    p_th.add_argument("--visual", default="")

    args = parser.parse_args()

    _setup_paths()
    if args.cmd != "thumbnail":
        _select_llm_provider()

    if args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "upload-last":
        cmd_upload_last(args)
    elif args.cmd == "tweet":
        cmd_tweet(args)
    elif args.cmd == "thumbnail":
        cmd_thumbnail(args)
    else:
        parser.error(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
