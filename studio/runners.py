# studio/runners.py — Real pipeline runners for MoneyPrinter Studio API
#
# Each runner walks the same stages the CLI walks (topic → script → metadata →
# prompts → images → thumbnail → tts → render), but emits SSE events at each
# step AND pauses at editable stages so the user can review/edit before the
# next stage runs.
#
# The pause/resume contract:
#   - emit `stage.start` then run the stage
#   - emit `stage.done` with artifacts
#   - call `pause_at(job_id, "<stage>")` → blocks until /continue is POSTed
#   - apply user edits returned in `payload`, then proceed to the next stage
#
# The runner is given:
#   emit(job_id, event_dict)
#   set_status(job_id, status_str)
#   set_artifact(job_id, key, path)
#   get_status(job_id)             optional, used to short-circuit on "cancelled"
#   set_instance(job_id, obj)      optional, lets api_server reuse the YouTube/
#                                  MovieSummary instance for the upload step.
#   pause_at(job_id, stage)        optional, blocks until /continue is POSTed.
#                                  Returns the user-supplied payload dict.
#
# pause_at is optional so cron-style headless callers can pass `None` and run
# without any gates.

import os
import sys

# Defensive sys.path patch for callers that import runners.py directly
# (e.g. tests). When the API server imports us, it has already pinned
# sys.path[0] to <project>/src so config.ROOT_DIR resolves correctly;
# we don't undo that.
_STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_STUDIO_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if not (sys.path[0] == _SRC_DIR or sys.path[0] == _PROJECT_ROOT):
    # Only repoint sys.path[0] if it's clearly wrong (e.g. we were run
    # from somewhere unrelated). Prefer SRC_DIR so config.ROOT_DIR =
    # dirname(SRC_DIR) = PROJECT_ROOT.
    sys.path[0] = _SRC_DIR
for _p in (_SRC_DIR, _PROJECT_ROOT, _STUDIO_DIR):
    if _p not in sys.path:
        sys.path.insert(1, _p)

import json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_dir(job_id: str) -> str:
    from config import ROOT_DIR
    d = os.path.join(ROOT_DIR, ".mp", "jobs", job_id)
    os.makedirs(d, exist_ok=True)
    return d


def _save_text(job_id: str, name: str, text: str) -> str:
    d = _job_dir(job_id)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _save_json(job_id: str, name: str, data) -> str:
    d = _job_dir(job_id)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _build_yt_kwargs(account: dict, cfg: dict) -> dict:
    from config import get_tts_voice
    kwargs = {
        "account_uuid": account.get("id"),
        "account_nickname": account.get("nickname", "Unknown"),
        "fp_profile_path": account.get("firefox_profile", ""),
        "niche": account.get("niche", ""),
        "language": account.get("language", ""),
        "image_style": cfg.get("image_style") or account.get("image_style", ""),
        "short_voice": cfg.get("voice_id") or account.get("short_voice", "") or get_tts_voice(),
        "long_voice": cfg.get("voice_id") or account.get("long_voice", "") or get_tts_voice(),
        "hook_profile": account.get("hook_profile", ""),
        "voice_drama": account.get("voice_drama", False),
    }
    if cfg.get("type") == "short":
        kwargs["target_duration_seconds"] = cfg.get("target_duration")
    return kwargs


def _split_paragraphs(text: str):
    """Same paragraph split the wizard uses, so the section indices the
    backend emits match the textareas the user sees."""
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]


def _maybe_pause(pause_at, job_id, stage):
    """Adapter so a None pause_at (headless mode) is a no-op."""
    if pause_at is None:
        return {}
    payload = pause_at(job_id, stage)
    return payload or {}


def _apply_script_edits(yt, payload):
    """If the user edited the script in the wizard, override yt.script before
    the next stage runs. Accepts either a flat string or a list of paragraphs."""
    if not payload:
        return
    if "script" in payload and isinstance(payload["script"], str):
        yt.script = payload["script"]
    elif "sections" in payload and isinstance(payload["sections"], list):
        yt.script = "\n\n".join(s for s in payload["sections"] if isinstance(s, str))


def _apply_metadata_edits(yt, payload):
    if not payload:
        return
    md = dict(getattr(yt, "metadata", {}) or {})
    if isinstance(payload.get("title"), str):
        md["title"] = payload["title"]
    if isinstance(payload.get("description"), str):
        md["description"] = payload["description"]
    if md:
        yt.metadata = md


def _apply_prompts_edits(yt, payload):
    if not payload:
        return
    prompts = payload.get("prompts")
    if isinstance(prompts, list):
        yt.image_prompts = [str(p) for p in prompts if str(p).strip()]


# ---------------------------------------------------------------------------
# Short-form pipeline
# ---------------------------------------------------------------------------

def run_short_job(job_id, cfg, emit, set_status, set_artifact,
                  get_status=None, set_instance=None, pause_at=None):
    """Run the full Short video pipeline with per-stage SSE events and
    optional pause-and-edit gates between editable stages."""
    from classes.YouTube import YouTube
    from classes.Tts import TTS
    from cache import get_accounts

    accounts = get_accounts("youtube")
    account = next((a for a in accounts if a.get("id") == cfg.get("account_id")), None)
    if not account:
        raise ValueError(f"Account {cfg.get('account_id')} not found")

    yt = YouTube(**_build_yt_kwargs(account, cfg))
    if set_instance:
        set_instance(job_id, yt)
    yt._is_long_video = False
    set_status(job_id, "running")
    emit(job_id, {"type": "running", "message": "Short video pipeline started"})

    def _cancelled() -> bool:
        if get_status and get_status(job_id) == "cancelled":
            emit(job_id, {"type": "cancelled", "message": "Job cancelled by user"})
            return True
        return False

    meta_path = None
    try:
        # ------------------------------------------------------------ topic
        emit(job_id, {"type": "stage.start", "stage": "topic", "message": "Generating topic..."})
        if _cancelled():
            return
        if cfg.get("topic"):
            yt.subject = cfg["topic"].strip()
        else:
            yt.generate_topic()
        set_artifact(job_id, "topic", yt.subject)
        emit(job_id, {"type": "stage.done", "stage": "topic", "artifacts": {"topic": yt.subject}})

        # ------------------------------------------------------------ script
        emit(job_id, {"type": "stage.start", "stage": "script", "message": "Generating script..."})
        if _cancelled():
            return
        yt.generate_script()
        script_path = _save_text(job_id, "script.txt", yt.script)
        for idx, para in enumerate(_split_paragraphs(yt.script)):
            emit(job_id, {"type": "stage.partial", "stage": "script", "index": idx, "chunk": para})
        set_artifact(job_id, "script", script_path)
        emit(job_id, {"type": "stage.done", "stage": "script", "artifacts": {"script": script_path}})

        # PAUSE: let the user edit the script before metadata is generated.
        edits = _maybe_pause(pause_at, job_id, "script")
        _apply_script_edits(yt, edits)
        if edits:
            script_path = _save_text(job_id, "script.txt", yt.script)
            set_artifact(job_id, "script", script_path)

        # ------------------------------------------------------------ metadata
        emit(job_id, {"type": "stage.start", "stage": "metadata", "message": "Generating metadata..."})
        if _cancelled():
            return
        yt.generate_metadata()
        meta_path = _save_json(job_id, "metadata.json", yt.metadata)
        set_artifact(job_id, "metadata", meta_path)
        emit(job_id, {"type": "stage.done", "stage": "metadata", "artifacts": {"metadata": meta_path}})

        # ------------------------------------------------------------ prompts
        emit(job_id, {"type": "stage.start", "stage": "prompts", "message": "Generating image prompts..."})
        if _cancelled():
            return
        yt.generate_prompts(image_mode=cfg.get("image_mode", "ai"))
        prompts_path = _save_json(job_id, "prompts.json", yt.image_prompts)
        set_artifact(job_id, "prompts", prompts_path)
        for idx, p in enumerate(yt.image_prompts):
            emit(job_id, {"type": "stage.partial", "stage": "prompts", "index": idx, "chunk": p})
        emit(job_id, {"type": "stage.done", "stage": "prompts", "artifacts": {"prompts": prompts_path}})

        # PAUSE: let the user edit/regenerate prompts before images render.
        edits = _maybe_pause(pause_at, job_id, "prompts")
        _apply_prompts_edits(yt, edits)
        if edits and "prompts" in edits:
            prompts_path = _save_json(job_id, "prompts.json", yt.image_prompts)
            set_artifact(job_id, "prompts", prompts_path)

        # ------------------------------------------------------------ images
        image_mode = cfg.get("image_mode", "ai")
        n_prompts = len(yt.image_prompts)
        emit(job_id, {"type": "stage.start", "stage": "images", "message": f"Generating {n_prompts} images..."})
        if _cancelled():
            return
        yt.generate_images_batch(yt.image_prompts, image_mode=image_mode)
        total_images = max(1, len(yt.images))
        for i, img_path in enumerate(yt.images):
            set_artifact(job_id, f"image/{i}", img_path)
            emit(job_id, {
                "type": "stage.progress",
                "stage": "images",
                "current": i + 1,
                "total": total_images,
                "percent": int(((i + 1) / total_images) * 100),
                "message": f"Image {i + 1}/{total_images}",
            })
        image_artifacts = {f"image/{i}": p for i, p in enumerate(yt.images)}
        emit(job_id, {"type": "stage.done", "stage": "images", "artifacts": image_artifacts})

        # ------------------------------------------------------------ thumbnail
        emit(job_id, {"type": "stage.start", "stage": "thumbnail", "message": "Generating thumbnail..."})
        if _cancelled():
            return
        yt.generate_thumbnail()
        set_artifact(job_id, "thumbnail", yt.thumbnail_path)
        emit(job_id, {"type": "stage.done", "stage": "thumbnail", "artifacts": {"thumbnail": yt.thumbnail_path}})

        # PAUSE: let the user replace title/overlay/theme. We don't re-render
        # the thumbnail here (that's a more involved op); the upload stage
        # uses whatever the user finally accepts as yt.thumbnail_path.
        _maybe_pause(pause_at, job_id, "thumbnail")

        # ------------------------------------------------------------ tts
        emit(job_id, {"type": "stage.start", "stage": "tts", "message": "Generating narration..."})
        if _cancelled():
            return
        tts = TTS()
        yt.generate_script_to_speech(tts)
        set_artifact(job_id, "audio", yt.tts_path)
        emit(job_id, {"type": "stage.done", "stage": "tts", "artifacts": {"audio": yt.tts_path}})

        # PAUSE: voice review. The user can listen to the audio artifact;
        # if they continue, we render. If they cancel, the gate is broken
        # by JobManager.cancel().
        _maybe_pause(pause_at, job_id, "narration")

        # ------------------------------------------------------------ render
        emit(job_id, {"type": "stage.start", "stage": "render", "message": "Rendering video..."})
        if _cancelled():
            return
        video_path = yt.combine()
        # Pin the rendered path on the instance so the upload endpoint can
        # reuse this exact instance (it does `instance.upload_video()` which
        # reads `self.video_path`). Without this, upload_video() refuses
        # with "no video was generated".
        yt.video_path = video_path
        set_artifact(job_id, "video", video_path)
        if yt.thumbnail_path:
            set_artifact(job_id, "thumbnail", yt.thumbnail_path)
        if getattr(yt, "tts_path", None):
            set_artifact(job_id, "audio", yt.tts_path)
        if getattr(yt, "metadata", None):
            meta_path = _save_json(job_id, "metadata.json", yt.metadata)
            set_artifact(job_id, "metadata", meta_path)
        emit(job_id, {"type": "stage.done", "stage": "render", "artifacts": {"video": video_path}})

        set_status(job_id, "done")
        emit(job_id, {
            "type": "done",
            "message": "Pipeline complete",
            "artifacts": {
                "video": video_path,
                "thumbnail": yt.thumbnail_path,
                "audio": getattr(yt, "tts_path", None),
                "metadata": meta_path if getattr(yt, "metadata", None) else None,
            },
        })
    except Exception as e:
        emit(job_id, {"type": "stage.error", "stage": "render", "message": str(e)})
        emit(job_id, {"type": "error", "message": str(e)})
        set_status(job_id, "error")


# ---------------------------------------------------------------------------
# Long-form pipeline (sectional, section-editable like the short pipeline)
# ---------------------------------------------------------------------------

def run_long_job(job_id, cfg, emit, set_status, set_artifact,
                 get_status=None, set_instance=None, pause_at=None):
    """Long-form pipeline. Mirrors the CLI's `_generate_long_video_inner`
    but exposes the same per-stage gates as the short pipeline so the user
    can review/edit script + prompts before images and TTS run.
    """
    from classes.YouTube import YouTube
    from classes.Tts import TTS, LONG_VIDEO_NARRATOR
    from cache import get_accounts
    from config import resolve_series, get_long_video_llm_model
    from llm_provider import force_provider, warmup_ollama_model
    from utils import expand_spoken_symbols, expand_regnal_numerals, expand_spanish_numbers
    from moviepy.editor import AudioFileClip
    from uuid import uuid4
    import re

    accounts = get_accounts("youtube")
    account = next((a for a in accounts if a.get("id") == cfg.get("account_id")), None)
    if not account:
        raise ValueError(f"Account {cfg.get('account_id')} not found")

    yt = YouTube(**_build_yt_kwargs(account, cfg))
    if set_instance:
        set_instance(job_id, yt)
    yt._is_long_video = True
    yt.images = []
    yt.image_prompts = []
    yt.word_timestamps = None
    yt.tts_path = None
    yt.subtitles_path = None
    yt._used_stock_urls = set()
    yt.thumbnail_path = ""

    set_status(job_id, "running")
    emit(job_id, {"type": "running", "message": "Long video pipeline started"})

    long_model = get_long_video_llm_model()
    warmup_ollama_model(long_model)

    def _cancelled() -> bool:
        if get_status and get_status(job_id) == "cancelled":
            emit(job_id, {"type": "cancelled", "message": "Job cancelled by user"})
            return True
        return False

    meta_path = None
    try:
        with force_provider("ollama", long_model):
            # ------------------------------------------------------ topic
            emit(job_id, {"type": "stage.start", "stage": "topic", "message": "Generating topic..."})
            if _cancelled():
                return
            if cfg.get("topic"):
                yt.subject = cfg["topic"].strip()
            else:
                yt.generate_topic()
            yt.active_series, yt.subject = resolve_series(yt.subject)
            set_artifact(job_id, "topic", yt.subject)
            emit(job_id, {"type": "stage.done", "stage": "topic", "artifacts": {"topic": yt.subject}})

            # ------------------------------------------------------ script
            emit(job_id, {"type": "stage.start", "stage": "script", "message": "Generating long script (this can take 1-3 min)..."})
            if _cancelled():
                return
            yt.generate_long_script()
            script_path = _save_text(job_id, "script.txt", yt.script)
            for idx, para in enumerate(_split_paragraphs(yt.script)):
                emit(job_id, {"type": "stage.partial", "stage": "script", "index": idx, "chunk": para})
            set_artifact(job_id, "script", script_path)
            emit(job_id, {"type": "stage.done", "stage": "script", "artifacts": {"script": script_path}})

            edits = _maybe_pause(pause_at, job_id, "script")
            _apply_script_edits(yt, edits)
            if edits:
                script_path = _save_text(job_id, "script.txt", yt.script)
                set_artifact(job_id, "script", script_path)

            # ------------------------------------------------------ metadata
            emit(job_id, {"type": "stage.start", "stage": "metadata", "message": "Generating metadata..."})
            if _cancelled():
                return
            yt.generate_long_metadata()
            meta_path = _save_json(job_id, "metadata.json", yt.metadata)
            set_artifact(job_id, "metadata", meta_path)
            emit(job_id, {"type": "stage.done", "stage": "metadata", "artifacts": {"metadata": meta_path}})

            # ------------------------------------------------------ thumbnail
            emit(job_id, {"type": "stage.start", "stage": "thumbnail", "message": "Generating thumbnail..."})
            if _cancelled():
                return
            try:
                yt.generate_thumbnail()
                set_artifact(job_id, "thumbnail", yt.thumbnail_path)
            except Exception as e:
                emit(job_id, {"type": "log", "level": "warn", "message": f"Thumbnail generation failed: {e}"})
                yt.thumbnail_path = ""
            emit(job_id, {"type": "stage.done", "stage": "thumbnail",
                          "artifacts": {"thumbnail": yt.thumbnail_path or ""}})

            _maybe_pause(pause_at, job_id, "thumbnail")

            # ------------------------------------------------------ prompts
            emit(job_id, {"type": "stage.start", "stage": "prompts", "message": "Generating image prompts..."})
            if _cancelled():
                return
            yt.generate_long_prompts()
            prompts_path = _save_json(job_id, "prompts.json", yt.image_prompts)
            set_artifact(job_id, "prompts", prompts_path)
            for idx, p in enumerate(yt.image_prompts):
                emit(job_id, {"type": "stage.partial", "stage": "prompts", "index": idx, "chunk": p})
            emit(job_id, {"type": "stage.done", "stage": "prompts", "artifacts": {"prompts": prompts_path}})

            edits = _maybe_pause(pause_at, job_id, "prompts")
            _apply_prompts_edits(yt, edits)
            if edits and "prompts" in edits:
                prompts_path = _save_json(job_id, "prompts.json", yt.image_prompts)
                set_artifact(job_id, "prompts", prompts_path)

            # ------------------------------------------------------ images
            n_prompts = len(yt.image_prompts)
            emit(job_id, {"type": "stage.start", "stage": "images",
                          "message": f"Generating {n_prompts} landscape images..."})
            if _cancelled():
                return
            yt.generate_long_images(yt.image_prompts)
            total_images = max(1, len(yt.images))
            for i, img_path in enumerate(yt.images):
                set_artifact(job_id, f"image/{i}", img_path)
                emit(job_id, {
                    "type": "stage.progress",
                    "stage": "images",
                    "current": i + 1,
                    "total": total_images,
                    "percent": int(((i + 1) / total_images) * 100),
                    "message": f"Image {i + 1}/{total_images}",
                })
            image_artifacts = {f"image/{i}": p for i, p in enumerate(yt.images)}
            emit(job_id, {"type": "stage.done", "stage": "images", "artifacts": image_artifacts})

            # ------------------------------------------------------ tts
            emit(job_id, {"type": "stage.start", "stage": "tts", "message": "Generating long-form narration..."})
            if _cancelled():
                return
            tts = TTS()
            from config import ROOT_DIR
            audio_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")
            tts_text = yt._clean_script_for_tts(yt.script)
            if not tts_text or len(tts_text.split()) < 50:
                tts_text = re.sub(r'\[.*?\]', '', yt.script).strip()
            tts_text = expand_spoken_symbols(tts_text)
            tts_text = expand_regnal_numerals(tts_text)
            tts_text = expand_spanish_numbers(tts_text)
            long_vid = yt._resolve_voice(yt._long_voice) or LONG_VIDEO_NARRATOR
            lang = (yt.language or "").strip().lower()
            is_spanish = lang.startswith("esp") or lang in {"es", "spanish"}
            if is_spanish and not long_vid.lower().startswith("es-"):
                long_vid = LONG_VIDEO_NARRATOR
            tts.synthesize_long(tts_text, audio_path, voice_id=long_vid)
            yt.tts_path = audio_path
            set_artifact(job_id, "audio", audio_path)
            try:
                dur = AudioFileClip(audio_path).duration
                emit(job_id, {"type": "log", "level": "info",
                              "message": f"Audio duration: {dur:.0f}s ({dur/60:.1f} min)"})
            except Exception:
                pass
            emit(job_id, {"type": "stage.done", "stage": "tts", "artifacts": {"audio": audio_path}})

            _maybe_pause(pause_at, job_id, "narration")

            # ------------------------------------------------------ render
            emit(job_id, {"type": "stage.start", "stage": "render", "message": "Assembling final video (15-25 min total render)..."})
            if _cancelled():
                return
            video_path = yt.combine_long()
            yt.video_path = video_path  # see comment in run_short_job
            set_artifact(job_id, "video", video_path)
            if getattr(yt, "metadata", None):
                meta_path = _save_json(job_id, "metadata.json", yt.metadata)
                set_artifact(job_id, "metadata", meta_path)
            emit(job_id, {"type": "stage.done", "stage": "render", "artifacts": {"video": video_path}})

            set_status(job_id, "done")
            emit(job_id, {
                "type": "done",
                "message": "Long video pipeline complete",
                "artifacts": {
                    "video": video_path,
                    "thumbnail": yt.thumbnail_path or None,
                    "audio": yt.tts_path,
                    "metadata": meta_path if getattr(yt, "metadata", None) else None,
                },
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        emit(job_id, {"type": "stage.error", "stage": "render", "message": str(e)})
        emit(job_id, {"type": "error", "message": str(e)})
        set_status(job_id, "error")


# ---------------------------------------------------------------------------
# Recap pipeline (kept monolithic — gates would require splitting MovieSummary)
# ---------------------------------------------------------------------------

def run_recap_job(job_id, cfg, emit, set_status, set_artifact,
                  get_status=None, set_instance=None, pause_at=None):
    """Run the movie recap (MovieSummary) pipeline. The MovieSummary class
    doesn't expose per-section hooks, so this stays one long stage.
    pause_at is accepted but unused here."""
    from classes.MovieSummary import MovieSummary
    from classes.Tts import TTS
    from cache import get_accounts

    accounts = get_accounts("youtube")
    account = next((a for a in accounts if a.get("id") == cfg.get("account_id")), None)
    if not account:
        raise ValueError(f"Account {cfg.get('account_id')} not found")

    ms = MovieSummary(**_build_yt_kwargs(account, cfg))
    if set_instance:
        set_instance(job_id, ms)
    tts = TTS()

    set_status(job_id, "running")
    emit(job_id, {"type": "running", "message": "Movie recap pipeline started"})

    def _cancelled() -> bool:
        if get_status and get_status(job_id) == "cancelled":
            emit(job_id, {"type": "cancelled", "message": "Job cancelled by user"})
            return True
        return False

    try:
        emit(job_id, {"type": "stage.start", "stage": "render", "message": "Generating movie summary..."})
        if _cancelled():
            return
        video_path = ms.generate_movie_summary(
            tts_instance=tts,
            movie_title=cfg.get("topic") or cfg.get("movie_title", ""),
            archive_identifier=cfg.get("archive_identifier"),
        )
        artifacts = {"video": video_path}
        if ms.thumbnail_path:
            set_artifact(job_id, "thumbnail", ms.thumbnail_path)
            artifacts["thumbnail"] = ms.thumbnail_path
        emit(job_id, {"type": "stage.done", "stage": "render", "artifacts": artifacts})

        set_status(job_id, "done")
        emit(job_id, {"type": "done", "message": "Pipeline complete", "artifacts": artifacts})
    except Exception as e:
        emit(job_id, {"type": "stage.error", "stage": "render", "message": str(e)})
        emit(job_id, {"type": "error", "message": str(e)})
        set_status(job_id, "error")
