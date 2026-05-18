"""
MoneyPrinter Largo — job runner (subprocess driver).

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
import json
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


def _classify_model(model_id: str) -> str:
    """Best-effort provider inference from a model id string.

    Gemini ids start with 'gemini-' or 'gemma-'; OpenAI ids start with 'gpt-'
    / 'o' / 'chatgpt-'; Ollama tags contain a colon (e.g. 'llama3:8b',
    Claude ids/aliases start with 'claude-' or are 'sonnet' / 'opus' / 'haiku';
    'gemma4:31b-cloud'). Everything else falls back to Pollinations since its
    catalog uses short alphanumeric ids."""
    m = (model_id or "").strip().lower()
    if not m:
        return ""
    if m.startswith("gemini-") or m.startswith("gemma-"):
        return "gemini"
    if m.startswith("gpt-") or m.startswith("chatgpt-") or m.startswith(("o1", "o3", "o4")):
        return "openai"
    if m.startswith("claude-") or m in {"sonnet", "opus", "haiku"}:
        return "claude"
    if ":" in m:
        return "ollama"
    return "pollinations"


def _select_llm_provider(override_provider: str = "", override_model: str = "", model_override: str = ""):
    """Pick the LLM provider + model.

    Three layered overrides, in order of precedence:
      1. (override_provider, override_model) — explicit pair from the new UI
         model picker. Wins absolutely; flips set_user_override(True) so the
         pipeline respects the choice instead of cross-falling back.
      2. model_override — single opaque model id; provider is inferred via
         `_classify_model` (legacy single-arg path used by batch jobs).
      3. Config defaults from config.json (no override at all)."""
    from config import (
        get_llm_provider, get_ollama_model,
    )
    from llm_provider import (
        normalize_gemini_model_id,
        select_model,
        set_llm_provider,
        list_models,
        set_user_override,
    )

    if override_provider:
        provider = override_provider
        set_llm_provider(provider)
        set_user_override(True)
        if override_model:
            if provider == "gemini":
                override_model = normalize_gemini_model_id(override_model) or override_model
            select_model(override_model)
            print(f"[runner] User override: provider={provider}, model={override_model}", flush=True)
        else:
            print(f"[runner] User override: provider={provider} (no model)", flush=True)
        return

    if model_override:
        inferred = _classify_model(model_override)
        if inferred == "gemini":
            model_override = normalize_gemini_model_id(model_override) or model_override
            set_llm_provider("gemini")
            # Tell the gemini code path to start with this model. We do it by
            # prepending it to the in-process gemini_models list via env var.
            os.environ["MP_GEMINI_MODEL_OVERRIDE"] = model_override
            print(f"[runner] Override: Gemini model {model_override}", flush=True)
            return
        if inferred == "openai":
            set_llm_provider("openai")
            select_model(model_override)
            print(f"[runner] Override: OpenAI model {model_override}", flush=True)
            return
        if inferred == "claude":
            set_llm_provider("claude")
            select_model(model_override)
            print(f"[runner] Override: Claude model {model_override}", flush=True)
            return
        if inferred == "ollama":
            set_llm_provider("ollama")
            select_model(model_override)
            print(f"[runner] Override: Ollama model {model_override}", flush=True)
            return
        if inferred == "pollinations":
            set_llm_provider("pollinations")
            select_model(model_override)
            print(f"[runner] Override: Pollinations model {model_override}", flush=True)
            return

    provider = get_llm_provider()
    set_llm_provider(provider)

    if provider == "gemini":
        print("[runner] Using Gemini provider", flush=True)
        return
    if provider == "openai":
        print("[runner] Using OpenAI provider", flush=True)
        return
    if provider == "claude":
        print("[runner] Using Claude provider", flush=True)
        return
    if provider == "pollinations":
        print("[runner] Using Pollinations provider", flush=True)
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


def _apply_openai_reasoning_effort(effort: str = "") -> None:
    effort = (effort or "").strip().lower()
    if not effort:
        return
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    if effort not in allowed:
        print(f"[runner] WARNING: ignoring invalid OpenAI thinking level {effort!r}", flush=True)
        return
    os.environ["MP_OPENAI_REASONING_EFFORT"] = effort
    print(f"[runner] OpenAI thinking level: {effort}", flush=True)


def _apply_image_provider(provider: str = "") -> None:
    provider = (provider or "").strip().lower()
    if not provider:
        return
    allowed = {"auto", "leonardo", "openai", "gemini"}
    if provider not in allowed:
        print(f"[runner] WARNING: ignoring invalid image provider {provider!r}", flush=True)
        return
    os.environ["MP_IMAGE_PROVIDER"] = provider
    print(f"[runner] Image provider: {provider}", flush=True)


def _apply_short_render_profile(profile: str) -> None:
    """Apply a complete per-job Short render profile via env vars.

    The lower-level config getters support individual overrides, so set the
    whole bundle here. That keeps the UI selector authoritative even when
    config.json contains custom defaults from a previous run.
    """
    profile = (profile or "").strip().lower()
    if not profile:
        return

    profiles = {
        "quality": {
            "MP_SHORT_RENDER_PROFILE": "quality",
            "MP_SHORT_RENDER_FPS": "30",
            "MP_SHORT_KEN_BURNS": "true",
            "MP_SHORT_KARAOKE_SUBTITLES": "true",
            "MP_SHORT_CROSSFADE_SECONDS": "0.4",
        },
        "fast": {
            "MP_SHORT_RENDER_PROFILE": "fast",
            "MP_SHORT_RENDER_FPS": "24",
            "MP_SHORT_KEN_BURNS": "false",
            "MP_SHORT_KARAOKE_SUBTITLES": "true",
            "MP_SHORT_CROSSFADE_SECONDS": "0",
        },
        "turbo": {
            "MP_SHORT_RENDER_PROFILE": "turbo",
            "MP_SHORT_RENDER_FPS": "24",
            "MP_SHORT_KEN_BURNS": "false",
            "MP_SHORT_KARAOKE_SUBTITLES": "false",
            "MP_SHORT_CROSSFADE_SECONDS": "0",
        },
    }
    selected = profiles.get(profile)
    if not selected:
        print(f"[runner] WARN: unknown render profile {profile!r}; using config defaults", flush=True)
        return

    os.environ.update(selected)
    print(f"[runner] Override: short_render_profile={profile}", flush=True)


# NOTE: the `.json` extension is load-bearing. rem_temp_files() wipes every
# non-(.json/.mp4) file in .mp/ on each pipeline run, so a parallel job for
# another channel would otherwise delete this pointer and upload-last would
# fall back to the global mtime scan.
_CHANNEL_REF_SUFFIX = ".last_video.json"


def _write_channel_ref(channel_id: str, video_path: str) -> None:
    """Record the path of the just-generated video so upload-last can find it
    without scanning the whole .mp/ directory. One file per channel so
    parallel jobs for different channels never interfere."""
    mp_dir = os.path.join(str(ROOT_DIR), ".mp")
    ref = os.path.join(mp_dir, f"{channel_id}{_CHANNEL_REF_SUFFIX}")
    try:
        with open(ref, "w", encoding="utf-8") as f:
            json.dump({"video_path": video_path, "channel_id": channel_id}, f)
    except Exception as e:
        print(f"[runner] WARN: could not write channel ref: {e}", flush=True)


def _read_channel_ref(channel_id: str) -> str:
    """Return the video path recorded by the last generate run, or ''."""
    mp_dir = os.path.join(str(ROOT_DIR), ".mp")
    for suffix in (_CHANNEL_REF_SUFFIX, ".last_video", ".last_video.txt"):
        ref = os.path.join(mp_dir, f"{channel_id}{suffix}")
        try:
            with open(ref, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    ref_channel = str(data.get("channel_id", "")).strip()
                    if ref_channel and ref_channel != channel_id:
                        continue
                    return str(data.get("video_path", "")).strip()
            except ValueError:
                pass
            # Legacy plain-path content (pre-JSON ref files).
            return raw
        except Exception:
            continue
    return ""


def _cleanup_after_upload(video_path: str, is_long: bool, channel_id: str = "") -> None:
    """Remove only the files that belong to the just-uploaded video.

    Safe to call while other parallel jobs are still running because it
    targets the specific UUID-named .mp4 / .meta.json rather than wiping
    the whole .mp/ directory. rem_temp_files() is still called to discard
    intermediate WAV/PNG/SRT scratch files (which are no longer needed once
    the video is rendered and uploaded)."""
    try:
        # Delete only this video's .mp4 (shorts; longs are kept for local use).
        if not is_long and video_path and os.path.isfile(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass

        # Delete this video's sidecar regardless of kind.
        sidecar = os.path.splitext(video_path)[0] + ".meta.json"
        if os.path.isfile(sidecar):
            try:
                os.remove(sidecar)
            except Exception:
                pass

        # Remove the per-channel ref pointer (upload consumed it).
        if channel_id:
            mp_dir = os.path.join(str(ROOT_DIR), ".mp")
            for suffix in (_CHANNEL_REF_SUFFIX, ".last_video", ".last_video.txt"):
                ref = os.path.join(mp_dir, f"{channel_id}{suffix}")
                if os.path.isfile(ref):
                    try:
                        os.remove(ref)
                    except Exception:
                        pass

        if not is_long:
            print("[runner] .mp cleaned after upload", flush=True)
        else:
            print("[runner] .mp scratch cleaned (long .mp4 preserved)", flush=True)
    except Exception as e:
        print(f"[runner] WARN: cleanup failed: {e}", flush=True)


def _upload_platforms_from_args(args) -> list[str]:
    from classes.SocialUpload import normalize_upload_platforms

    raw = getattr(args, "upload_platforms", "") or ""
    if getattr(args, "upload", False):
        raw = f"youtube,{raw}" if raw else "youtube"
    return normalize_upload_platforms(raw)


def cmd_generate(args):
    from cache import get_accounts
    from classes.SocialUpload import SocialUploader, format_platforms
    from classes.YouTube import YouTube
    from classes.Tts import TTS

    acc = next((a for a in get_accounts("youtube") if a.get("id") == args.channel_id), None)
    if not acc:
        print(f"[runner] ERROR: channel {args.channel_id} not found", flush=True)
        sys.exit(2)

    # Duration preset (60/120/180s) only applies to shorts; long videos ignore it.
    target_duration: int | None = None
    if args.kind == "short" and getattr(args, "duration", 0):
        from classes.duration_presets import ALLOWED_SHORT_DURATIONS
        if args.duration in ALLOWED_SHORT_DURATIONS:
            target_duration = args.duration
        else:
            print(
                f"[runner] WARN: duration {args.duration}s not in {ALLOWED_SHORT_DURATIONS}; using default",
                flush=True,
            )

    # Per-job hook_profile override (picks the opening style from HOOK_PROFILES
    # in src/classes/YouTube.py). Empty string means "use the channel default".
    hook_profile_override = (getattr(args, "hook_profile", "") or "").strip().lower()
    effective_hook = hook_profile_override or acc.get("hook_profile", "")

    # Per-job sentence length override — exposed as an env var so the existing
    # `get_script_sentence_length()` getter picks it up without us having to
    # plumb a parameter through every script-generation entry point.
    sl = getattr(args, "sentence_length", 0)
    if sl and sl > 0:
        os.environ["MP_SENTENCE_LENGTH_OVERRIDE"] = str(sl)
        print(f"[runner] Override: script_sentence_length={sl}", flush=True)

    hook_override = getattr(args, "hook_style", "") or ""
    if hook_override:
        os.environ["MP_HOOK_STYLE_OVERRIDE"] = hook_override
        print(f"[runner] Override: hook_style={hook_override}", flush=True)

    if args.kind == "short":
        _apply_short_render_profile(getattr(args, "render_profile", ""))

    retention_mode = (getattr(args, "retention_mode", "") or "").strip()
    if args.kind == "short" and retention_mode:
        print(f"[runner] Retention mode: {retention_mode}", flush=True)

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
        hook_profile=effective_hook,
        voice_drama=acc.get("voice_drama", False),
        target_duration_seconds=target_duration,
        retention_mode=retention_mode,
    )
    if hook_profile_override:
        print(f"[runner] Hook profile override: {hook_profile_override}", flush=True)
    tts = TTS()

    # Pre-approved script from the "Vista previa" flow. File format: first
    # line = subject, then a blank line, then the script body. When present
    # we set those attributes directly so generate_video skips the LLM steps.
    preset_subject = ""
    preset_script = ""
    script_file = getattr(args, "script_file", "") or ""
    if script_file:
        try:
            with open(script_file, "r", encoding="utf-8") as f:
                raw = f.read()
            head, _, body = raw.partition("\n\n")
            preset_subject = (head or "").strip()
            preset_script = (body or "").strip()
            if preset_subject and preset_script:
                print(f"[runner] Using pre-approved script (subject={preset_subject[:60]!r}, "
                      f"len={len(preset_script)})", flush=True)
            else:
                print(f"[runner] WARN: script file malformed at {script_file}", flush=True)
                preset_subject = preset_script = ""
        except Exception as e:
            print(f"[runner] WARN: could not load script file {script_file}: {e}", flush=True)

    topic = args.topic or ""
    photo_input = (getattr(args, "photo_input", "") or "").strip()
    if preset_subject and not topic:
        topic = preset_subject

    if args.kind == "long":
        if args.series_id and topic and not topic.lstrip().startswith("["):
            topic = f"[{args.series_id}] {topic}"

    if photo_input:
        from classes.PhotoVideo import PhotoVideoGenerator, PhotoVideoRequest, collect_photo_paths

        photo_paths = collect_photo_paths(photo_input)
        if not photo_paths:
            print(f"[runner] ERROR: no valid photos found in {photo_input!r}", flush=True)
            sys.exit(2)
        label = "LONG video" if args.kind == "long" else "SHORT"
        print(
            f"[runner] Generating {label} from {len(photo_paths)} uploaded photo(s). "
            f"Topic: {topic or '(auto from photos)'}",
            flush=True,
        )
        path = PhotoVideoGenerator(youtube).generate(
            tts,
            PhotoVideoRequest(
                kind=args.kind,
                photo_paths=photo_paths,
                topic=topic,
                script=preset_script,
                auto_analyze=True,
            ),
        )
    elif args.kind == "long":
        print(f"[runner] Generating LONG video. Topic: {topic or '(auto)'}", flush=True)
        path = youtube.generate_long_video(tts, custom_topic=topic)
    else:
        print(f"[runner] Generating SHORT. Topic: {topic or '(auto)'}, image_mode={args.image_mode}", flush=True)
        if preset_subject and preset_script:
            youtube.subject = preset_subject
            youtube.script = preset_script
            path = youtube.generate_video(
                tts, custom_topic=preset_subject, image_mode=args.image_mode,
                preset_script=preset_script,
            )
        else:
            path = youtube.generate_video(tts, custom_topic=topic, image_mode=args.image_mode)

    if not path:
        print("[runner] ERROR: generation aborted (no video produced)", flush=True)
        sys.exit(3)

    print(f"[runner] Generated: {path}", flush=True)
    _write_channel_ref(args.channel_id, path)

    upload_platforms = _upload_platforms_from_args(args)
    try:
        from classes.SocialOptimizer import SUPPORTED_SOCIAL_PLATFORMS, ensure_social_plan

        metadata = getattr(youtube, "metadata", {}) or {}
        plan = ensure_social_plan(
            video_path=path,
            title=metadata.get("title", ""),
            description=metadata.get("description", ""),
            subject=getattr(youtube, "subject", "") or "",
            niche=acc.get("niche", ""),
            language=acc.get("language", "espanol"),
            platforms=upload_platforms or SUPPORTED_SOCIAL_PLATFORMS,
            is_long=(args.kind == "long"),
            thumbnail_path=getattr(youtube, "thumbnail_path", "") or "",
            account_uuid=args.channel_id,
        )
        qg = plan.get("quality_gate") or {}
        print(
            f"[runner] Social plan ready: quality={qg.get('status', 'unknown')} "
            f"score={qg.get('score', 'n/a')}",
            flush=True,
        )
    except Exception as exc:
        print(f"[runner] WARN: could not build social optimization plan: {exc}", flush=True)

    if upload_platforms:
        print(f"[runner] Starting upload to {format_platforms(upload_platforms)}...", flush=True)
        results = SocialUploader.from_youtube(youtube).upload(upload_platforms)
        print(f"[runner] Upload results: {results}", flush=True)
        if not results or not all(results.values()):
            sys.exit(4)
        _cleanup_after_upload(path, is_long=(args.kind == "long"), channel_id=args.channel_id)

    print("[runner] DONE", flush=True)


def cmd_preview_script(args):
    """Generate ONLY the subject + script (no images, no TTS, no render). Writes
    the result to .mp/.preview-<uuid>.txt and prints the uuid so the SSE
    consumer can fetch the content via GET /api/preview/<uuid>.

    This is the backend side of the "Vista previa" flow: the user reviews
    (and optionally edits) the script before the full render pipeline runs."""
    import uuid as _uuid

    from cache import get_accounts
    from classes.YouTube import YouTube

    acc = next((a for a in get_accounts("youtube") if a.get("id") == args.channel_id), None)
    if not acc:
        print(f"[runner] ERROR: channel {args.channel_id} not found", flush=True)
        sys.exit(2)

    sl = getattr(args, "sentence_length", 0)
    if sl and sl > 0:
        os.environ["MP_SENTENCE_LENGTH_OVERRIDE"] = str(sl)
        print(f"[runner] Override: script_sentence_length={sl}", flush=True)

    hook_override = getattr(args, "hook_style", "") or ""
    if hook_override:
        os.environ["MP_HOOK_STYLE_OVERRIDE"] = hook_override
        print(f"[runner] Override: hook_style={hook_override}", flush=True)

    retention_mode = (getattr(args, "retention_mode", "") or "").strip()
    if retention_mode:
        print(f"[runner] Retention mode: {retention_mode}", flush=True)

    print(f"[runner] Preview for channel '{acc.get('nickname')}'", flush=True)
    target_duration: int | None = None
    if getattr(args, "duration", 0):
        from classes.duration_presets import ALLOWED_SHORT_DURATIONS
        if args.duration in ALLOWED_SHORT_DURATIONS:
            target_duration = args.duration
            print(f"[runner] Preview duration preset: {target_duration}s", flush=True)
        else:
            print(
                f"[runner] WARN: preview duration {args.duration}s not in {ALLOWED_SHORT_DURATIONS}; using default",
                flush=True,
            )
    youtube = YouTube(
        acc["id"], acc["nickname"], acc.get("firefox_profile", ""),
        acc.get("niche", ""), acc.get("language", "español"),
        image_style=acc.get("image_style", ""),
        short_voice=acc.get("short_voice", ""),
        long_voice=acc.get("long_voice", ""),
        hook_profile=acc.get("hook_profile", ""),
        voice_drama=acc.get("voice_drama", False),
        target_duration_seconds=target_duration,
        retention_mode=retention_mode,
    )

    # Subject — custom or auto. We DON'T enforce dedupe here so the user can
    # iterate cheaply on the same topic until satisfied; the dedupe guard
    # runs again at full-generate time anyway.
    topic = (args.topic or "").strip()
    if topic:
        youtube.subject = topic
        print(f"[runner] Using custom topic: {topic}", flush=True)
    else:
        print("[runner] Generating topic...", flush=True)
        youtube.generate_topic()
        if not youtube.subject:
            print("[runner] ERROR: could not generate a unique topic", flush=True)
            sys.exit(3)

    print(f"[runner] Subject: {youtube.subject}", flush=True)
    print("[runner] Generating script...", flush=True)
    script = youtube.generate_script()
    if not script or not script.strip():
        print("[runner] ERROR: empty script returned by LLM", flush=True)
        sys.exit(3)

    preview_id = _uuid.uuid4().hex[:12]
    out_path = os.path.join(str(ROOT_DIR), ".mp", f".preview-{preview_id}.txt")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"{youtube.subject}\n\n{script}\n")
    except Exception as e:
        print(f"[runner] ERROR: could not write preview file: {e}", flush=True)
        sys.exit(4)

    # The SSE consumer parses this line to know the preview is ready.
    print(f"[runner] PREVIEW_ID={preview_id}", flush=True)
    print(f"[runner] DONE — {len(script)} chars in script", flush=True)


def cmd_preview_voice(args):
    """Generate only the narration audio from an existing preview script."""
    from cache import get_accounts
    from classes.ScriptVoicePreview import ScriptVoicePreview
    from classes.Tts import TTS

    acc = next((a for a in get_accounts("youtube") if a.get("id") == args.channel_id), None)
    if not acc:
        print(f"[runner] ERROR: channel {args.channel_id} not found", flush=True)
        sys.exit(2)

    preview_id = (getattr(args, "preview_id", "") or "").strip()
    script_file = (getattr(args, "script_file", "") or "").strip()
    if preview_id:
        script_file = os.path.join(str(ROOT_DIR), ".mp", f".preview-{preview_id}.txt")
    if not script_file:
        print("[runner] ERROR: --preview-id or --script-file is required", flush=True)
        sys.exit(2)
    if not os.path.isfile(script_file):
        print(f"[runner] ERROR: script file not found: {script_file}", flush=True)
        sys.exit(2)

    try:
        with open(script_file, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        print(f"[runner] ERROR: could not read script file: {e}", flush=True)
        sys.exit(4)

    subject, sep, script = raw.partition("\n\n")
    if not sep:
        script = subject
        subject = ""
    subject = subject.strip()
    script = script.strip()
    if not script:
        print("[runner] ERROR: script is empty", flush=True)
        sys.exit(3)

    retention_mode = (getattr(args, "retention_mode", "") or "").strip()
    print(f"[runner] Voice preview for channel '{acc.get('nickname')}'", flush=True)
    if retention_mode:
        print(f"[runner] Retention mode: {retention_mode}", flush=True)

    preview = ScriptVoicePreview.from_channel(
        acc,
        retention_mode=retention_mode,
        tts_instance=TTS(),
        output_dir=os.path.join(str(ROOT_DIR), ".mp"),
    )
    result = preview.synthesize(
        subject=subject,
        script=script,
        kind=getattr(args, "kind", "short"),
        preview_id=preview_id,
    )
    print(f"[runner] AUDIO_PATH={result.audio_path}", flush=True)
    print(f"[runner] AUDIO_DURATION={result.duration_seconds:.1f}", flush=True)
    print("[runner] DONE - voice-only preview ready", flush=True)


def cmd_upload_last(args):
    from cache import get_accounts
    from classes.SocialUpload import SocialUploader, format_platforms
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

    # Resolve which .mp4 to upload:
    # 1. Per-channel ref file written by cmd_generate — exact path, safe with
    #    parallel jobs because each channel has its own pointer file.
    # 2. Fallback: newest .mp4 whose sidecar's channel_id matches THIS channel.
    #    The fallback never considers videos belonging to another channel (or
    #    sidecar-less videos), so a missing ref pointer can no longer cause a
    #    cross-channel upload.
    mp_dir = os.path.join(str(ROOT_DIR), ".mp")
    ref_path = _read_channel_ref(args.channel_id)
    if ref_path and os.path.isfile(ref_path):
        youtube.video_path = ref_path
        print(f"[runner] Resolved via channel ref: {ref_path}", flush=True)
    else:
        candidates = []
        if os.path.isdir(mp_dir):
            for name in os.listdir(mp_dir):
                if not name.lower().endswith(".mp4"):
                    continue
                p = os.path.join(mp_dir, name)
                sc = os.path.splitext(p)[0] + ".meta.json"
                if not os.path.isfile(sc):
                    continue
                try:
                    with open(sc, "r", encoding="utf-8") as f:
                        sc_channel = json.load(f).get("channel_id", "")
                except Exception:
                    continue
                if sc_channel != args.channel_id:
                    continue
                try:
                    candidates.append((os.path.getmtime(p), p))
                except OSError:
                    pass
        if not candidates:
            print(
                "[runner] ERROR: no video found for this channel to upload "
                f"(channel {args.channel_id}). The per-channel pointer was "
                "missing and no .mp4 with a matching sidecar exists. "
                "Regenerate the video for this channel and upload again.",
                flush=True,
            )
            sys.exit(5)
        candidates.sort(reverse=True)
        chosen = candidates[0][1]
        youtube.video_path = chosen
        print(f"[runner] Resolved via channel-scoped mtime scan: {chosen}", flush=True)

    # Load the sidecar (`<basename>.meta.json`) that the generation step wrote
    # so we recover subject + title + description. Without this, upload_video
    # bails out with "subject is empty" because a fresh subprocess has no
    # in-memory state from the prior generation.
    sidecar_path = os.path.splitext(youtube.video_path)[0] + ".meta.json"
    is_long_from_sidecar = None
    if os.path.isfile(sidecar_path):
        try:
            import json as _json
            with open(sidecar_path, "r", encoding="utf-8") as f:
                meta = _json.load(f)
            youtube.subject = meta.get("subject", "") or ""
            md = meta.get("metadata") or {}
            if md:
                youtube.metadata = md
            tp = meta.get("thumbnail_path", "")
            if tp:
                youtube.thumbnail_path = tp
            if "is_long" in meta:
                is_long_from_sidecar = bool(meta["is_long"])
            print(f"[runner] Loaded sidecar: subject={youtube.subject[:60]!r}", flush=True)
        except Exception as e:
            print(f"[runner] WARN: could not load sidecar {sidecar_path}: {e}", flush=True)
    else:
        print(f"[runner] WARN: no sidecar at {sidecar_path} — will recover metadata from audio via Whisper", flush=True)

    # Sidecar's is_long takes precedence over the user-passed --kind because
    # the sidecar reflects what was actually generated.
    is_long = is_long_from_sidecar if is_long_from_sidecar is not None else (args.kind == "long")
    youtube._is_long_video = is_long

    # When the sidecar is missing or didn't yield a subject + metadata pair,
    # mirror the CLI "Re-upload last video" flow: delegate to reupload_video,
    # which transcribes the audio with Whisper and asks the LLM for a title +
    # description from the actual spoken script. The result is persisted to a
    # fresh sidecar so the next retry skips this work.
    has_metadata = bool(
        (getattr(youtube, "subject", "") or "").strip()
        and (getattr(youtube, "metadata", None) or {}).get("title")
        and (getattr(youtube, "metadata", None) or {}).get("description")
    )
    if not has_metadata:
        print(
            f"[runner] No subject/metadata found — recovering from audio with Whisper "
            f"(uploading {'LONG' if is_long else 'SHORT'}: {youtube.video_path})",
            flush=True,
        )
        try:
            ok = youtube.reupload_video(
                youtube.video_path,
                subject=None,
                is_long=is_long,
                upload=False,
            )
        except Exception as e:
            print(f"[runner] ERROR: Whisper-based recovery failed: {type(e).__name__}: {e}", flush=True)
            sys.exit(4)
    else:
        print(f"[runner] Metadata ready for {'LONG' if is_long else 'SHORT'}: {youtube.video_path}", flush=True)

    upload_platforms = _upload_platforms_from_args(args)
    if not upload_platforms:
        upload_platforms = ["youtube"]

    print(f"[runner] Uploading to {format_platforms(upload_platforms)}: {youtube.video_path}", flush=True)
    results = SocialUploader.from_youtube(youtube).upload(upload_platforms)
    print(f"[runner] Upload results: {results}", flush=True)
    if not results or not all(results.values()):
        sys.exit(4)

    _cleanup_after_upload(youtube.video_path, is_long=is_long, channel_id=args.channel_id)


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


def cmd_sync_yt(args):
    """Run scripts/sync_youtube_cache.py with the requested flags. Streams
    its stdout straight through to the SSE consumer so the user sees the
    live per-video progress in the dialog."""
    script = os.path.join(str(ROOT_DIR), "scripts", "sync_youtube_cache.py")
    if not os.path.isfile(script):
        print(f"[runner] ERROR: sync script not found at {script}", flush=True)
        sys.exit(2)

    cmd = [sys.executable, script, "--apply"]
    if args.prune:
        cmd.append("--prune")
    if args.add_missing:
        cmd.append("--add")
    if args.refresh_meta:
        cmd.append("--refresh-meta")
    elif args.refresh_dates:
        cmd.append("--refresh-dates")
    if args.channel_id:
        cmd += ["--channel-id", args.channel_id]

    print(f"[runner] Syncing YouTube cache: {' '.join(cmd[2:])}", flush=True)
    import subprocess
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = proc.wait()
    if rc != 0:
        print(f"[runner] Sync failed (rc={rc})", flush=True)
        sys.exit(rc)
    print("[runner] Sync complete", flush=True)


def cmd_tweet(args):
    from cache import get_accounts
    from config import get_firefox_profile_path
    from classes.Twitter import Twitter

    acc = next((a for a in get_accounts("twitter") if a.get("id") == args.account_id), None)
    if not acc:
        print(f"[runner] ERROR: twitter account {args.account_id} not found", flush=True)
        sys.exit(2)
    firefox_profile = acc.get("firefox_profile", "") or get_firefox_profile_path()
    tw = Twitter(acc["id"], acc["nickname"], firefox_profile, acc.get("topic", ""))
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
    p_gen.add_argument("--image-provider", default="",
                       help="AI image provider for image_mode=ai: auto, leonardo, openai, gemini.")
    p_gen.add_argument("--upload", action="store_true")
    p_gen.add_argument("--upload-platforms", default="",
                       help="Comma-separated upload targets: youtube,tiktok,facebook. --upload still means youtube.")
    p_gen.add_argument("--series-id", default="")
    # Target short duration in seconds (60/120/180). 0 = use legacy default.
    p_gen.add_argument("--duration", type=int, default=0)
    # Per-job LLM override picked from the new (Channel page) UI picker —
    # explicit (provider, model) pair. Empty = use config defaults.
    p_gen.add_argument("--llm-provider", default="")
    p_gen.add_argument("--llm-model", default="")
    p_gen.add_argument("--llm-reasoning-effort", default="",
                       help="OpenAI/Codex thinking level: low, medium, high, xhigh.")
    # Per-job hook profile override (educational / storytelling / ...). Empty = use channel default.
    p_gen.add_argument("--hook-profile", default="")
    # Per-job overrides — let the UI pick a specific model and an estimated
    # short duration (mapped to script_sentence_length) without mutating the
    # global config.json. The single-arg --model path infers provider via
    # `_classify_model` and is used by the batch generator + preview flow.
    p_gen.add_argument("--model", default="",
                       help="Override LLM model for this job only (e.g. gemini-2.5-flash, llama3:8b).")
    p_gen.add_argument("--sentence-length", type=int, default=0,
                       help="Override script_sentence_length (number of sentences in the short).")
    p_gen.add_argument("--hook-style", default="",
                       help="Override the per-run hook style. Format: '<profile>::<style_name>'.")
    p_gen.add_argument("--render-profile", choices=["quality", "fast", "turbo"], default="",
                       help="Override Short render profile for this job only.")
    p_gen.add_argument("--retention-mode", choices=["standard", "maxima_retencion"], default="",
                       help="Short creative mode. Use maxima_retencion for tighter hooks, faster pacing and more visuals.")
    p_gen.add_argument("--script-file", default="",
                       help="Path to a pre-approved script file. When set, generation skips "
                            "subject + script steps and reuses what's in the file.")
    p_gen.add_argument("--photo-input", default="",
                       help="Folder or file list of user-uploaded photos to use as the only visuals.")

    p_pv = sub.add_parser("preview-script")
    p_pv.add_argument("--channel-id", required=True)
    p_pv.add_argument("--topic", default="")
    p_pv.add_argument("--model", default="")
    p_pv.add_argument("--llm-provider", default="")
    p_pv.add_argument("--llm-model", default="")
    p_pv.add_argument("--llm-reasoning-effort", default="",
                      help="OpenAI/Codex thinking level: low, medium, high, xhigh.")
    p_pv.add_argument("--sentence-length", type=int, default=0)
    p_pv.add_argument("--duration", type=int, default=0)
    p_pv.add_argument("--hook-style", default="")
    p_pv.add_argument("--retention-mode", choices=["standard", "maxima_retencion"], default="")

    p_voice = sub.add_parser("preview-voice")
    p_voice.add_argument("--channel-id", required=True)
    p_voice.add_argument("--kind", choices=["short", "long"], default="short")
    p_voice.add_argument("--preview-id", default="")
    p_voice.add_argument("--script-file", default="")
    p_voice.add_argument("--retention-mode", choices=["standard", "maxima_retencion"], default="")

    p_ul = sub.add_parser("upload-last")
    p_ul.add_argument("--channel-id", required=True)
    p_ul.add_argument("--kind", choices=["short", "long"], default="short")
    p_ul.add_argument("--upload-platforms", default="",
                      help="Comma-separated upload targets: youtube,tiktok,facebook.")

    p_tw = sub.add_parser("tweet")
    p_tw.add_argument("--account-id", required=True)

    p_th = sub.add_parser("thumbnail")
    p_th.add_argument("--topic", required=True)
    p_th.add_argument("--text", required=True)
    p_th.add_argument("--out", required=True)
    p_th.add_argument("--visual", default="")

    p_sy = sub.add_parser("sync-yt")
    p_sy.add_argument("--prune", action="store_true")
    p_sy.add_argument("--add-missing", action="store_true")
    p_sy.add_argument("--refresh-meta", action="store_true")
    p_sy.add_argument("--refresh-dates", action="store_true")
    p_sy.add_argument("--channel-id", default="")

    args = parser.parse_args()

    _setup_paths()
    if args.cmd not in ("thumbnail", "preview-voice"):
        _apply_openai_reasoning_effort(getattr(args, "llm_reasoning_effort", "") or "")
        if args.cmd == "generate":
            _apply_image_provider(getattr(args, "image_provider", "") or "")
        # The explicit (--llm-provider, --llm-model) pair from the Channel UI
        # wins over --model (single-arg, used by batch + preview). Both feed
        # the same _select_llm_provider entry point so the runner stays simple.
        ov_provider = getattr(args, "llm_provider", "") or ""
        ov_model = getattr(args, "llm_model", "") or ""
        legacy_override = getattr(args, "model", "") if args.cmd in ("generate", "preview-script") else ""
        _select_llm_provider(
            override_provider=ov_provider,
            override_model=ov_model,
            model_override=legacy_override,
        )

    if args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "preview-script":
        cmd_preview_script(args)
    elif args.cmd == "preview-voice":
        cmd_preview_voice(args)
    elif args.cmd == "upload-last":
        cmd_upload_last(args)
    elif args.cmd == "tweet":
        cmd_tweet(args)
    elif args.cmd == "thumbnail":
        cmd_thumbnail(args)
    elif args.cmd == "sync-yt":
        cmd_sync_yt(args)
    else:
        parser.error(f"unknown command {args.cmd}")


if __name__ == "__main__":
    main()
