"""
Backend API server for MoneyPrinter Studio.

Provides:
  - YouTube Studio scraping (existing)
  - Health checks (existing)
  - Config read-only endpoints (series, voices, accounts)
  - Preset CRUD
  - Job lifecycle + SSE streaming for async pipeline steps
  - TTS preview endpoint
  - Artifact serving (script, prompts, metadata, images, thumbnail, audio, video)
  - Upload endpoint (spawns Selenium upload on a cached instance)
"""

import json
import os
import sys
import time
import uuid
import threading
import random
from typing import Any

# ---------------------------------------------------------------------------
# 1. sys.path fix — module-level
#
# `config.ROOT_DIR` is computed as `os.path.dirname(sys.path[0])` at import
# time. If we run uvicorn from `studio/`, sys.path[0] would be `studio/`
# and ROOT_DIR would resolve to the parent of the project — one level too
# high — so `cache.get_youtube_cache_path()` would point at a non-existent
# `.mp/` dir.
#
# We replace sys.path[0] with `<project>/src` so `config.ROOT_DIR =
# dirname(sys.path[0])` lands on the actual project root. We also keep
# `studio/` reachable so this module can still `from runners import ...`.
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path[0] = SRC_DIR
for p in (ROOT_DIR, STUDIO_DIR):
    if p not in sys.path:
        sys.path.insert(1, p)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

app = FastAPI(title="MoneyPrinter Studio API")

# 4. Update CORS origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE_DIR = os.path.join(ROOT_DIR, ".mp")
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
PRESETS_PATH = os.path.join(CACHE_DIR, "presets.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 9. Extend JobManager
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}
        self._clients = {}
        self._status = {}
        self._results = {}
        self._instances = {}  # job_id -> YouTube/MovieSummary instance
        # Per-job gate state. The runner thread blocks on `_gates[job_id]`
        # at editable stages (script / prompts / thumbnail / narration);
        # the user releases it via POST /api/jobs/{job_id}/continue.
        self._gates = {}        # job_id -> threading.Event
        self._gate_stage = {}   # job_id -> str (stage name currently waiting)
        self._gate_payload = {} # job_id -> dict (last payload posted via /continue)
        # Summary state used by GET /api/jobs (the task monitor list view).
        # We update these via emit() so we don't have to rescan every event.
        self._created_at = {}    # job_id -> ISO timestamp
        self._current_stage = {} # job_id -> last "stage.start" or "stage.progress"
        self._stage_message = {} # job_id -> message of the current stage event
        self._stage_percent = {} # job_id -> int (0..100), only when emitted
        self._last_log = {}      # job_id -> last "log" event message
        self._final_url = {}     # job_id -> str (set on stage.done for "upload")

    def create(self):
        job_id = str(uuid.uuid4())
        with self._lock:
            self._events[job_id] = []
            self._clients[job_id] = []
            self._status[job_id] = "queued"
            self._results[job_id] = {"artifacts": {}}
            self._gates[job_id] = threading.Event()
            self._gate_stage[job_id] = None
            self._gate_payload[job_id] = None
            self._created_at[job_id] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._current_stage[job_id] = None
            self._stage_message[job_id] = ""
            self._stage_percent[job_id] = None
            self._last_log[job_id] = ""
            self._final_url[job_id] = None
        return job_id

    def list_jobs(self):
        """Snapshot of every job in memory, in creation order. Used by the
        Task Monitor page to render its card grid."""
        out = []
        with self._lock:
            for jid in self._events.keys():
                cfg = self._results.get(jid, {}) or {}
                artifacts = cfg.get("artifacts", {}) if isinstance(cfg, dict) else {}
                out.append({
                    "job_id": jid,
                    "type": cfg.get("type", "short"),
                    "topic": cfg.get("topic", ""),
                    "account_id": cfg.get("account_id", ""),
                    "status": self._status.get(jid, "unknown"),
                    "current_stage": self._current_stage.get(jid),
                    "stage_message": self._stage_message.get(jid, ""),
                    "stage_percent": self._stage_percent.get(jid),
                    "awaiting": self._gate_stage.get(jid),
                    "last_log": self._last_log.get(jid, ""),
                    "created_at": self._created_at.get(jid),
                    "video_url": self._final_url.get(jid),
                    "has_video": bool(artifacts.get("video")),
                    "has_thumbnail": bool(artifacts.get("thumbnail")),
                })
        # Newest first so the active job is at the top
        out.sort(key=lambda j: (j.get("created_at") or "", j["job_id"]), reverse=True)
        return out

    # ---- pause / continue gates -------------------------------------------

    def pause_at(self, job_id, stage):
        """Mark `stage` as awaiting user confirmation. Emits a SSE event so
        the UI can switch its Continue button into enabled state, then
        blocks the runner thread until release_gate is called."""
        with self._lock:
            evt = self._gates.get(job_id)
            if evt is None:
                return False
            self._gate_stage[job_id] = stage
            self._gate_payload[job_id] = None
            evt.clear()
        self.emit(job_id, {
            "type": "stage.awaiting",
            "stage": stage,
            "message": f"Awaiting user review for stage '{stage}'",
        })
        evt.wait()  # block runner thread
        with self._lock:
            payload = self._gate_payload.get(job_id) or {}
            self._gate_stage[job_id] = None
        return payload

    def release_gate(self, job_id, stage, payload=None):
        """Called by /api/jobs/{job_id}/continue. Returns True if the gate
        was waiting on this stage, False if the gate is closed or on a
        different stage (caller should 400)."""
        with self._lock:
            evt = self._gates.get(job_id)
            current = self._gate_stage.get(job_id)
            if evt is None:
                return False
            if current and stage and current != stage:
                return False
            self._gate_payload[job_id] = payload or {}
            evt.set()
        self.emit(job_id, {
            "type": "stage.resumed",
            "stage": stage or current,
            "message": f"User confirmed stage '{stage or current}', resuming",
        })
        return True

    def gate_status(self, job_id):
        with self._lock:
            return self._gate_stage.get(job_id)

    def emit(self, job_id, event):
        with self._lock:
            if job_id not in self._events:
                return
            self._events[job_id].append(event)
            for client_queue in self._clients.get(job_id, []):
                client_queue.append(event)
            # Mirror summary state so /api/jobs (the task monitor list) doesn't
            # have to walk the full event log on each poll.
            etype = event.get("type", "")
            if etype == "stage.start":
                self._current_stage[job_id] = event.get("stage")
                self._stage_message[job_id] = event.get("message", "")
                self._stage_percent[job_id] = None
            elif etype == "stage.progress":
                self._current_stage[job_id] = event.get("stage")
                self._stage_message[job_id] = event.get("message", "")
                pct = event.get("percent")
                if isinstance(pct, (int, float)) and pct > 0:
                    self._stage_percent[job_id] = int(pct)
            elif etype == "stage.done":
                if event.get("stage") == "upload":
                    url = (event.get("artifacts") or {}).get("upload_url")
                    if url:
                        self._final_url[job_id] = url
            elif etype == "log":
                msg = event.get("message", "")
                if msg:
                    self._last_log[job_id] = msg
            elif etype == "done":
                arts = event.get("artifacts") or {}
                v = arts.get("video")
                if isinstance(v, str) and v.startswith("http"):
                    self._final_url[job_id] = v

    def status(self, job_id):
        with self._lock:
            return self._status.get(job_id, "unknown")

    def set_status(self, job_id, status):
        with self._lock:
            if job_id in self._status:
                self._status[job_id] = status

    def set_result(self, job_id, result):
        with self._lock:
            self._results[job_id] = result

    def get_result(self, job_id):
        with self._lock:
            return self._results.get(job_id)

    # 7. Add _add_artifact → set_artifact
    def set_artifact(self, job_id, key, path):
        with self._lock:
            if job_id not in self._results:
                return
            self._results[job_id].setdefault("artifacts", {})[key] = path

    def get_artifact(self, job_id, key):
        with self._lock:
            return self._results.get(job_id, {}).get("artifacts", {}).get(key)

    def cancel(self, job_id):
        with self._lock:
            if job_id not in self._status:
                return False
            if self._status[job_id] in ("done", "error"):
                return False
            self._status[job_id] = "cancelled"
        # 12. SSE taxonomy: use "cancelled"
        self.emit(job_id, {"type": "cancelled", "message": "Job cancelled by user"})
        return True

    def _client_stream(self, job_id):
        client_queue = []
        with self._lock:
            if job_id not in self._clients:
                return
            self._clients[job_id].append(client_queue)
            idx = len(self._events.get(job_id, []))

        while True:
            time.sleep(0.05)
            with self._lock:
                new_events = client_queue[idx:]
                idx += len(new_events)
                status = self._status.get(job_id, "unknown")
                if status in ("done", "error", "cancelled"):
                    try:
                        self._clients[job_id].remove(client_queue)
                    except ValueError:
                        pass
            for ev in new_events:
                if ev.get("type") == "_keepalive":
                    yield ":keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
            if status in ("done", "error", "cancelled"):
                yield f"data: {json.dumps({'type': status, 'message': f'Job {status}'})}\n\n"
                break

    def stream(self, job_id):
        with self._lock:
            if job_id not in self._events:
                raise HTTPException(status_code=404, detail="Job not found")
        return StreamingResponse(
            self._client_stream(job_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    def cleanup(self, job_id):
        """Remove job state and temporary files after terminal status."""
        with self._lock:
            self._events.pop(job_id, None)
            self._clients.pop(job_id, None)
            self._status.pop(job_id, None)
            self._results.pop(job_id, None)
            instance = self._instances.pop(job_id, None)
            # Release any waiting gate so the runner thread can unblock
            # and exit cleanly during cleanup.
            evt = self._gates.pop(job_id, None)
            if evt is not None:
                evt.set()
            self._gate_stage.pop(job_id, None)
            self._gate_payload.pop(job_id, None)
            # Drop summary state so /api/jobs stops listing this job.
            self._created_at.pop(job_id, None)
            self._current_stage.pop(job_id, None)
            self._stage_message.pop(job_id, None)
            self._stage_percent.pop(job_id, None)
            self._last_log.pop(job_id, None)
            self._final_url.pop(job_id, None)
        # Best-effort temp dir cleanup for Firefox profiles held by instances
        if instance is not None:
            try:
                temp_dir = getattr(instance, "_temp_profile_dir", None)
                if temp_dir and os.path.isdir(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    def schedule_cleanup(self, job_id, delay_seconds=3600):
        """Schedule cleanup after a delay for terminal jobs."""
        def _do():
            time.sleep(delay_seconds)
            self.cleanup(job_id)
        threading.Thread(target=_do, daemon=True).start()


jobs = JobManager()


# ---------------------------------------------------------------------------
# YouTube studio scraping
# ---------------------------------------------------------------------------

def scrape_youtube_studio():
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service
    import shutil
    import tempfile
    import re

    fp_path = _get_firefox_profile()
    if not fp_path or not os.path.isdir(fp_path):
        return _fallback_data()

    options = FirefoxOptions()
    options.page_load_strategy = "eager"
    options.set_preference("app.update.enabled", False)
    options.set_preference("dom.ipc.processCount", 1)
    try:
        options.add_argument("--headless")
    except Exception:
        pass

    temp_dir = tempfile.mkdtemp(prefix="mpv2_firefox_")
    temp_profile = os.path.join(temp_dir, "profile")
    shutil.copytree(
        fp_path, temp_profile,
        ignore=shutil.ignore_patterns(
            "lock", ".parentlock", "parent.lock",
            "cache2", "startupCache", "shader-cache",
            "thumbnails", "storage", "crashes",
            "sessionstore.jsonlz4", "sessionstore-backups",
        ),
        dirs_exist_ok=False,
    )
    options.add_argument("-profile")
    options.add_argument(temp_profile)

    driver = None
    videos = []
    try:
        from webdriver_manager.firefox import GeckoDriverManager
        driver_path = GeckoDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(30)
        driver.get("https://studio.youtube.com")
        time.sleep(3)
        channel_id = None
        try:
            channel_id = driver.current_url.split("/")[-1]
        except Exception:
            pass
        content_url = f"https://studio.youtube.com/channel/{channel_id}/videos" if channel_id else "https://studio.youtube.com"
        driver.get(content_url)
        time.sleep(5)
        videos = _parse_studio_page(driver, channel_id)
    except Exception as e:
        print(f"[API] Selenium scrape failed: {e}", file=sys.stderr)
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
    return videos if videos else _fallback_data()


def _get_firefox_profile():
    data = load_json(os.path.join(CACHE_DIR, "youtube.json"), {"accounts": []})
    accounts = data.get("accounts", [])
    if not accounts:
        return None
    return accounts[0].get("firefox_profile")


def _parse_studio_page(driver, channel_id):
    from selenium.webdriver.common.by import By
    import re
    raw = _extract_via_js(driver)
    if raw:
        return raw

    videos = []
    thumbnail_elements = driver.find_elements(By.TAG_NAME, "ytcp-video-thumbnail")
    titles = driver.find_elements(By.CSS_SELECTOR, "#video-title, ytcp-video-title")
    metric_rows = driver.find_elements(By.CSS_SELECTOR, "ytcp-video-list-cell-metrics, .metrics-row")

    if not thumbnail_elements:
        return _fallback_data()

    for i, thumb in enumerate(thumbnail_elements[:50]):
        title_text = titles[i].text if i < len(titles) else "Unknown"
        video_id = None
        try:
            inner = thumb.get_attribute("innerHTML")
            m = re.search(r'/video/([a-zA-Z0-9_-]+)', inner)
            if not m:
                m = re.search(r'video_id["\s:=]+["\']([a-zA-Z0-9_-]+)', inner)
            if m:
                video_id = m.group(1)
        except Exception:
            pass
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else ""
        video_url = f"https://youtube.com/watch?v={video_id}" if video_id else ""
        views = "—"
        likes = "—"
        comments = "—"
        if i < len(metric_rows):
            try:
                metrics = metric_rows[i].text
                v = re.search(r'([\d,.KkMm]+)\s*(?:views|visualizaciones)', metrics)
                if v:
                    views = v.group(1)
                l = re.search(r'([\d,.KkMm]+)\s*(?:likes|me gusta)', metrics)
                if l:
                    likes = l.group(1)
                c = re.search(r'([\d,.KkMm]+)\s*(?:comments|comentarios)', metrics)
                if c:
                    comments = c.group(1)
            except Exception:
                pass
        videos.append({
            "id": video_id or f"video-{i}",
            "title": title_text or f"Video {i + 1}",
            "thumbnail": thumbnail_url,
            "url": video_url,
            "views": views,
            "likes": likes,
            "comments": comments,
            "published": "",
        })

    return videos if videos else _fallback_data()


def _extract_via_js(driver):
    try:
        result = driver.execute_script("""
            var videos = [];
            var scripts = document.querySelectorAll('script[nonce]');
            for (var s of scripts) {
                if (!s.textContent) continue;
                if (s.textContent.includes('"videoId"') || s.textContent.includes('"title"')) {
                    try {
                        var data = JSON.parse(s.textContent);
                        if (data.contents && data.contents.twoColumnBrowseResultsRenderer) {
                            var tabs = data.contents.twoColumnBrowseResultsRenderer.tabs;
                            tabs.forEach(function(tab) {
                                var items = (tab.tabRenderer && tab.tabRenderer.content && tab.tabRenderer.content.sectionListRenderer && tab.tabRenderer.content.sectionListRenderer.contents) || [];
                                items.forEach(function(section) {
                                    var grid = (section.itemSectionRenderer && section.itemSectionRenderer.contents) || [];
                                    grid.forEach(function(item) {
                                        var vr = (item.gridVideoRenderer || item.videoRenderer || item.videoWithContextRenderer);
                                        if (vr && vr.videoId && vr.title) {
                                            videos.push({
                                                id: vr.videoId,
                                                title: (vr.title.runs || []).map(r => r.text).join(''),
                                                thumbnail: 'https://i.ytimg.com/vi/' + vr.videoId + '/mqdefault.jpg',
                                                url: 'https://youtube.com/watch?v=' + vr.videoId,
                                                views: (vr.viewCountText || {}).simpleText || '—',
                                                likes: '—',
                                                comments: '—',
                                                published: (vr.publishedTimeText || {}).simpleText || ''
                                            });
                                        }
                                    });
                                });
                            });
                        }
                    } catch(e) {}
                }
            }
            return videos;
        """)
        if result and len(result) > 0:
            return result
    except Exception:
        pass
    return None


def _fallback_data():
    return [
        {"id": "fallback-1", "title": "El Misterio del Universo: Agujeros Negros Explicados", "thumbnail": "", "url": "", "views": "12.4K", "likes": "843", "comments": "126", "published": "hace 3 días"},
        {"id": "fallback-2", "title": "Viaje al Centro de la Galaxia: Lo que la NASA no te cuenta", "thumbnail": "", "url": "", "views": "8.7K", "likes": "612", "comments": "89", "published": "hace 1 semana"},
        {"id": "fallback-3", "title": "¿Qué pasaría si el Sol desapareciera mañana?", "thumbnail": "", "url": "", "views": "45.2K", "likes": "2.1K", "comments": "340", "published": "hace 2 semanas"},
        {"id": "fallback-4", "title": "Documental: Los Secretos de Marte revelados", "thumbnail": "", "url": "", "views": "3.2K", "likes": "278", "comments": "45", "published": "hace 3 semanas"},
        {"id": "fallback-5", "title": "Teoría del Multiverso: ¿Existen copias tuyas en otros universos?", "thumbnail": "", "url": "", "views": "28.9K", "likes": "1.4K", "comments": "210", "published": "hace 1 mes"},
        {"id": "fallback-6", "title": "Los 5 Planetas más Extraños del Universo Conocido", "thumbnail": "", "url": "", "views": "19.3K", "likes": "956", "comments": "132", "published": "hace 1 mes"},
    ]


# ---------------------------------------------------------------------------
# 2. Update _infer_voices() and _infer_accounts()
# ---------------------------------------------------------------------------

def _infer_voices():
    voice = "Jasper"
    try:
        from config import get_tts_voice
        voice = get_tts_voice()
    except Exception:
        pass

    known = {
        "Jasper":   {"id": "en-US-GuyNeural",       "alias": "Jasper",  "lang": "en", "gender": "male"},
        "Bella":    {"id": "en-US-JennyNeural",     "alias": "Bella",   "lang": "en", "gender": "female"},
        "Luna":     {"id": "en-US-AriaNeural",      "alias": "Luna",    "lang": "en", "gender": "female"},
        "Bruno":    {"id": "en-US-DavisNeural",     "alias": "Bruno",   "lang": "en", "gender": "male"},
        "Rosie":    {"id": "en-US-SaraNeural",      "alias": "Rosie",   "lang": "en", "gender": "female"},
        "Hugo":     {"id": "en-GB-RyanNeural",      "alias": "Hugo",    "lang": "en", "gender": "male"},
        "Kiki":     {"id": "en-AU-NatashaNeural",   "alias": "Kiki",    "lang": "en", "gender": "female"},
        "Leo":      {"id": "en-US-ChristopherNeural", "alias": "Leo",   "lang": "en", "gender": "male"},
        "Sofia":    {"id": "es-MX-DaliaNeural",      "alias": "Sofia",   "lang": "es", "gender": "female"},
        "Carlos":   {"id": "es-MX-JorgeNeural",      "alias": "Carlos",  "lang": "es", "gender": "male"},
        "Elena":    {"id": "es-ES-ElviraNeural",     "alias": "Elena",   "lang": "es", "gender": "female"},
        "Pablo":    {"id": "es-ES-EliasNeural",      "alias": "Pablo",   "lang": "es", "gender": "male"},
        "Alvaro":   {"id": "es-ES-AlvaroNeural",     "alias": "Alvaro",  "lang": "es", "gender": "male"},
    }
    out = []
    for v in known.values():
        entry = dict(v)
        entry["default"] = (entry["alias"] == voice)
        out.append(entry)
    return out


def _infer_accounts():
    data = load_json(os.path.join(CACHE_DIR, "youtube.json"), {"accounts": []})
    accounts = []
    for a in data.get("accounts", []):
        fp_path = a.get("firefox_profile", "")
        accounts.append({
            "id": a.get("id"),
            "nickname": a.get("nickname", "Unknown"),
            "niche": a.get("niche", ""),
            "language": a.get("language", ""),
            "image_style": a.get("image_style", ""),
            "short_voice": a.get("short_voice", ""),
            "long_voice": a.get("long_voice", ""),
            "profile_ready": bool(fp_path and os.path.isdir(fp_path)),
            "firefox_profile": fp_path,
            "hook_profile": a.get("hook_profile", ""),
            "voice_drama": a.get("voice_drama", False),
        })
    return accounts


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def _load_presets():
    return load_json(PRESETS_PATH, [])


def _save_presets(presets):
    save_json(PRESETS_PATH, presets)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/youtube/videos")
def get_youtube_videos():
    try:
        videos = scrape_youtube_studio()
        return {"videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 3. Update /api/health
@app.get("/api/health")
def health_check():
    from config import get_imagemagick_path
    fp = _get_firefox_profile()
    has_profile = bool(fp and os.path.isdir(fp))
    try:
        imagemagick_ok = os.path.isfile(get_imagemagick_path())
    except Exception:
        imagemagick_ok = False
    return {
        "status": "ok",
        "version": "2.0.0",
        "firefox_profile_ready": has_profile,
        "imagemagick_ok": imagemagick_ok,
        "accounts_configured": len(_infer_accounts()),
        "presets_saved": len(_load_presets()),
    }


@app.get("/api/config")
def get_config():
    raw = load_config()
    return {
        "llm_provider": raw.get("llm_provider", "ollama"),
        "ollama_base_url": raw.get("ollama_base_url", ""),
        "ollama_model": raw.get("ollama_model", ""),
        "gemini_models": raw.get("gemini_models", []),
        "nanobanana2_model": raw.get("nanobanana2_model", ""),
        "nanobanana2_aspect_ratio": raw.get("nanobanana2_aspect_ratio", "9:16"),
        "tts_voice": raw.get("tts_voice", "Jasper"),
        "tts_provider": raw.get("tts_provider", "edge_tts"),
        "stt_provider": raw.get("stt_provider", "local_whisper"),
        "whisper_model": raw.get("whisper_model", "base"),
        "font": raw.get("font", ""),
        "imagemagick_path": raw.get("imagemagick_path", ""),
        "threads": raw.get("threads", 2),
        "movie_max_duration_seconds": raw.get("movie_max_duration_seconds", 1200),
        "movie_chunk_minutes": raw.get("movie_chunk_minutes", 25),
    }


@app.get("/api/config/series")
def get_series():
    raw = load_config()
    series = raw.get("series", [])
    out = []
    for s in series:
        brief = s.get("script_brief", "")
        out.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "title_template": s.get("title_template"),
            "thumbnail_overlay": s.get("thumbnail_overlay"),
            "thumbnail_font": s.get("thumbnail_font"),
            "script_brief": (brief[:200] + "...") if len(brief) > 200 else brief,
            "section_count": len(s.get("section_themes", [])),
        })
    return {"series": out}


@app.get("/api/config/voices")
def get_voices():
    voices = _infer_voices()
    default = "Jasper"
    for v in voices:
        if v.get("default"):
            default = v["alias"]
            break
    return {"voices": voices, "default": default}


@app.get("/api/accounts")
def get_accounts():
    return {"accounts": _infer_accounts()}


@app.get("/api/presets")
def get_presets():
    return {"presets": _load_presets()}


@app.post("/api/presets")
def create_preset(data: dict):
    presets = _load_presets()
    preset = {
        "id": str(uuid.uuid4()),
        "name": data.get("name", "Untitled"),
        "type": data.get("type", "short"),
        "voice_id": data.get("voice_id", ""),
        "image_style": data.get("image_style", ""),
        "thumbnail": data.get("thumbnail", {}),
        "narrative_prompt": data.get("narrative_prompt", ""),
        "created_at": time.time(),
    }
    presets.append(preset)
    _save_presets(presets)
    return {"preset": preset}


@app.put("/api/presets/{preset_id}")
def update_preset(preset_id: str, data: dict):
    presets = _load_presets()
    idx = None
    for i, p in enumerate(presets):
        if p["id"] == preset_id:
            idx = i
            break
    if idx is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    presets[idx].update(data)
    _save_presets(presets)
    return {"preset": presets[idx]}


@app.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str):
    presets = _load_presets()
    new_presets = [p for p in presets if p["id"] != preset_id]
    if len(new_presets) == len(presets):
        raise HTTPException(status_code=404, detail="Preset not found")
    _save_presets(new_presets)
    return {"deleted": True}


def _coerce_duration(raw):
    """Validate incoming target_duration and return a canonical value."""
    from classes.duration_presets import ALLOWED_SHORT_DURATIONS, DEFAULT_SHORT_DURATION
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SHORT_DURATION
    return val if val in ALLOWED_SHORT_DURATIONS else DEFAULT_SHORT_DURATION


# --- Jobs ------------------------------------------------------------------

# 6. Update POST /api/jobs body parsing
@app.post("/api/jobs")
def create_job(data: dict):
    job_id = jobs.create()
    cfg = {
        "type": data.get("type", "short"),
        "account_id": data.get("account_id"),
        "topic": data.get("topic", ""),
        "series_id": data.get("series_id"),
        "voice_id": data.get("voice_id", ""),
        "image_mode": data.get("image_mode", "ai"),
        "image_style": data.get("image_style", ""),
        "preset_id": data.get("preset_id"),
        "target_duration": _coerce_duration(data.get("target_duration")),
    }
    jobs.set_result(job_id, cfg)
    jobs.emit(job_id, {"type": "queued", "message": "Job queued", "job_id": job_id})
    thread = threading.Thread(target=_run_pipeline, args=(job_id, cfg), daemon=True)
    thread.start()
    return {"job_id": job_id}


# Task Monitor — list view. Returns ALL jobs currently in memory (running,
# awaiting user input, or recently terminal but not yet cleaned up). Newest
# first. The frontend polls this every 2s.
@app.get("/api/jobs")
def list_jobs():
    return {"jobs": jobs.list_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    result = jobs.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": jobs.status(job_id),
        "config": result,
        "artifacts": result.get("artifacts", {}),
    }


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    return jobs.stream(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    ok = jobs.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot cancel this job")
    return {"cancelled": True}


# 8b. POST /api/jobs/{job_id}/continue
#
# Releases the per-stage gate held by the runner thread. Body shape:
#
#   { "stage": "script", "payload": { "script": "...edited text..." } }
#
# Supported stages and payload keys:
#   - "script"     → { "script": str } (overrides yt.script before next stage)
#   - "metadata"   → { "title": str, "description": str }
#   - "prompts"    → { "prompts": [str, ...] } (overrides yt.image_prompts)
#   - "thumbnail"  → { "title": str, "overlay": str, "font": str, "theme": str }
#   - "narration"  → { "voice_id": str, "drama": int, "pacing": int }
#
# Stage names not waiting → 400. The runner reads the payload via
# `JobManager.pause_at(...)` which returns it from the wait.
@app.post("/api/jobs/{job_id}/continue")
def continue_job(job_id: str, data: dict):
    if jobs.status(job_id) == "unknown":
        raise HTTPException(status_code=404, detail="Job not found")
    stage = data.get("stage")
    payload = data.get("payload", {}) or {}
    current = jobs.gate_status(job_id)
    if current is None:
        raise HTTPException(
            status_code=400,
            detail="Job is not currently awaiting user confirmation",
        )
    if stage and stage != current:
        raise HTTPException(
            status_code=400,
            detail=f"Job is awaiting stage '{current}', not '{stage}'",
        )
    ok = jobs.release_gate(job_id, stage or current, payload)
    if not ok:
        raise HTTPException(status_code=400, detail="Gate could not be released")
    return {"resumed": True, "stage": stage or current}


@app.get("/api/jobs/{job_id}/gate")
def get_gate_status(job_id: str):
    """Lets the UI re-sync the gate state on reconnect (e.g. after refresh)."""
    if jobs.status(job_id) == "unknown":
        raise HTTPException(status_code=404, detail="Job not found")
    return {"awaiting": jobs.gate_status(job_id)}


@app.post("/api/jobs/{job_id}/restart")
def restart_job(job_id: str):
    """Clone an existing job's config and spawn a fresh pipeline.

    The caller receives a new job_id; the new job starts from the very
    beginning (topic/script/etc.) using the original configuration.
    """
    result = jobs.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Corrupted job result")

    cfg = {
        "type": result.get("type", "short"),
        "account_id": result.get("account_id"),
        "topic": result.get("topic", ""),
        "series_id": result.get("series_id"),
        "voice_id": result.get("voice_id", ""),
        "image_mode": result.get("image_mode", "ai"),
        "image_style": result.get("image_style", ""),
        "preset_id": result.get("preset_id"),
        "target_duration": result.get("target_duration"),
    }
    new_job_id = jobs.create()
    jobs.set_result(new_job_id, cfg)
    jobs.emit(
        new_job_id,
        {"type": "queued", "message": "Job restarted from library", "job_id": new_job_id},
    )
    thread = threading.Thread(target=_run_pipeline, args=(new_job_id, cfg), daemon=True)
    thread.start()
    return {"job_id": new_job_id}


# --- TTS -------------------------------------------------------------------

# 5. Update POST /api/tts/preview
@app.post("/api/tts/preview")
def tts_preview(data: dict):
    text = data.get("text", "")
    voice_id = data.get("voice_id", "es-ES-AlvaroNeural")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    try:
        from classes.Tts import TTS
        tts = TTS()
        preview_path = os.path.join(CACHE_DIR, f"preview_{int(time.time())}.wav")
        tts.synthesize(text[:150], output_file=preview_path, voice_id=voice_id)
        return {"path": preview_path, "duration_seconds": 5}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Artifact routes -------------------------------------------------------

def _artifact_file_path(job_id: str, key: str) -> str:
    """Return the on-disk path for an artifact key, guarding against traversal."""
    path = jobs.get_artifact(job_id, key)
    if not path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    real = os.path.abspath(os.path.normpath(path))
    root = os.path.abspath(ROOT_DIR)
    # Prevent escaping above project root
    if not real.startswith(root + os.sep) and real != root:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return real


@app.get("/api/jobs/{job_id}/artifact/script")
def get_artifact_script(job_id: str):
    result = jobs.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    path = _artifact_file_path(job_id, "script")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    sections = [p.strip() for p in text.split("\n\n") if p.strip()]
    return {"script": text, "sections": sections}


@app.get("/api/jobs/{job_id}/artifact/prompts")
def get_artifact_prompts(job_id: str):
    path = _artifact_file_path(job_id, "prompts")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"prompts": data}


@app.get("/api/jobs/{job_id}/artifact/metadata")
def get_artifact_metadata(job_id: str):
    path = _artifact_file_path(job_id, "metadata")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.get("/api/jobs/{job_id}/artifact/image/{idx}")
def get_artifact_image(job_id: str, idx: int):
    path = _artifact_file_path(job_id, f"image/{idx}")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/artifact/thumbnail")
def get_artifact_thumbnail(job_id: str):
    path = _artifact_file_path(job_id, "thumbnail")
    return FileResponse(path, media_type="image/png")


@app.get("/api/jobs/{job_id}/artifact/audio")
def get_artifact_audio(job_id: str):
    path = _artifact_file_path(job_id, "audio")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/jobs/{job_id}/artifact/video")
def get_artifact_video(job_id: str):
    path = _artifact_file_path(job_id, "video")
    # FileResponse natively supports HTTP Range requests (206 Partial Content)
    return FileResponse(path, media_type="video/mp4")


# 11. POST /api/jobs/{job_id}/upload
#
# Body: { "confirm": true, "account_id": "<optional override>" }
#
# Spawns the Selenium upload on the cached YouTube instance for `job_id`.
# If the instance was lost (server restart, or job created via the recap
# pipeline that doesn't keep one around), reconstruct one from the artifacts
# we persisted under .mp/jobs/<job_id>/. Emits per-substep progress so
# UploadStage can show a meaningful banner instead of just a spinner.
@app.post("/api/jobs/{job_id}/upload")
def upload_job(job_id: str, data: dict):
    result = jobs.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    if not data.get("confirm"):
        raise HTTPException(status_code=400, detail="confirm: true required")

    override_account_id = data.get("account_id")

    artifacts = result.get("artifacts", {}) or {}
    instance = jobs._instances.get(job_id)
    if not instance:
        cfg = dict(result)
        if override_account_id:
            cfg["account_id"] = override_account_id
        account = next((a for a in _infer_accounts() if a.get("id") == cfg.get("account_id")), None)
        if not account:
            ready = [a for a in _infer_accounts() if a.get("profile_ready")]
            account = ready[0] if ready else None
        if not account:
            raise HTTPException(status_code=400, detail="No account configured for upload")
        from runners import _build_yt_kwargs
        from classes.YouTube import YouTube
        yt = YouTube(**_build_yt_kwargs(account, cfg))
        if "video" in artifacts:
            yt.video_path = artifacts["video"]
        if "thumbnail" in artifacts:
            yt.thumbnail_path = artifacts["thumbnail"]
        if "script" in artifacts:
            yt.subject = cfg.get("topic", "")
        try:
            meta_path = artifacts.get("metadata")
            if meta_path and os.path.isfile(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    yt.metadata = json.load(f)
        except Exception:
            pass
        instance = yt
        with jobs._lock:
            jobs._instances[job_id] = instance

    # Defensive hydration when an instance survived from the runner but
    # the runner forgot to pin paths/metadata onto it (regression caught
    # in the real-run smoke test). Always prefer existing instance values
    # so we don't clobber edits, but fill anything that's empty.
    if not getattr(instance, "video_path", None) and artifacts.get("video"):
        instance.video_path = artifacts["video"]
    if not getattr(instance, "thumbnail_path", None) and artifacts.get("thumbnail"):
        instance.thumbnail_path = artifacts["thumbnail"]
    if not getattr(instance, "subject", None):
        instance.subject = (result.get("topic") or "").strip()
    if not getattr(instance, "metadata", None) and artifacts.get("metadata"):
        try:
            with open(artifacts["metadata"], "r", encoding="utf-8") as f:
                instance.metadata = json.load(f)
        except Exception:
            pass

    # Pre-flight checks so we can return a clean 400 instead of
    # spawning a thread that immediately bails inside upload_video().
    vpath = getattr(instance, "video_path", "") or ""
    if not vpath or not os.path.isfile(vpath):
        raise HTTPException(
            status_code=400,
            detail=f"No rendered video available to upload (video_path='{vpath}'). "
                   "The render stage must complete successfully first."
        )

    account_id = override_account_id or result.get("account_id") or ""

    def _do_upload():
        # Stream key checkpoints by hooking the status module so the user
        # sees the same progress the CLI prints. We patch info/success
        # for the duration of upload_video() and forward each call as a
        # stage.progress event.
        from status import info as _orig_info, success as _orig_success, warning as _orig_warning
        import status as _status_mod

        def _emit(level, msg):
            jobs.emit(job_id, {
                "type": "log", "level": level,
                "message": str(msg),
                "account_id": account_id,
            })
            # Heuristic upload-stage progress hints from the status text.
            text = str(msg).lower()
            stage_msg = None
            if "channel id" in text or "navigating to upload" in text:
                stage_msg = "Opening YouTube Studio"
            elif "uploading file" in text:
                stage_msg = "Uploading video file"
            elif "setting title" in text:
                stage_msg = "Setting title"
            elif "setting description" in text:
                stage_msg = "Setting description"
            elif "uploading thumbnail" in text or "thumbnail upload attempt" in text:
                stage_msg = "Uploading custom thumbnail"
            elif "next button" in text or "clicking next" in text:
                stage_msg = "Advancing wizard"
            elif "setting visibility" in text:
                stage_msg = "Setting visibility"
            elif "clicking done" in text:
                stage_msg = "Submitting upload"
            elif "polling listing" in text or "still waiting" in text:
                stage_msg = "Waiting for YouTube to process"
            elif "upload + processing finished" in text:
                stage_msg = "Upload finished"
            elif "uploaded video:" in text:
                stage_msg = "Got public URL"
            if stage_msg:
                jobs.emit(job_id, {
                    "type": "stage.progress",
                    "stage": "upload",
                    "current": 0,
                    "total": 0,
                    "percent": 0,
                    "message": stage_msg,
                    "account_id": account_id,
                })

        def _patched_info(msg, *args, **kwargs):
            _emit("info", msg)
            return _orig_info(msg, *args, **kwargs)

        def _patched_success(msg, *args, **kwargs):
            _emit("info", msg)
            return _orig_success(msg, *args, **kwargs)

        def _patched_warning(msg, *args, **kwargs):
            _emit("warn", msg)
            return _orig_warning(msg, *args, **kwargs)

        _status_mod.info = _patched_info
        _status_mod.success = _patched_success
        _status_mod.warning = _patched_warning

        try:
            jobs.emit(job_id, {
                "type": "stage.start", "stage": "upload",
                "message": "Starting Selenium upload to YouTube...",
                "account_id": account_id,
            })
            jobs.set_status(job_id, "uploading")
            ok = instance.upload_video()
            uploaded_url = getattr(instance, "uploaded_video_url", "") or ""
            # YouTubeUploader.upload_video() returns bool — False means the
            # Selenium flow refused (missing file, missing subject, …) but
            # didn't raise. We MUST treat that as an error or the job ends
            # up "done" with nothing actually uploaded.
            if ok is False:
                msg = (
                    "upload_video() returned False — Selenium flow did not "
                    "complete the upload (check server logs for the reason)."
                )
                jobs.emit(job_id, {
                    "type": "stage.error", "stage": "upload",
                    "message": msg, "account_id": account_id,
                })
                jobs.emit(job_id, {"type": "error", "message": msg})
                jobs.set_status(job_id, "error")
                jobs.schedule_cleanup(job_id)
                return
            jobs.emit(job_id, {
                "type": "stage.done",
                "stage": "upload",
                "artifacts": {"upload_url": uploaded_url} if uploaded_url else {},
                "account_id": account_id,
            })
            jobs.set_status(job_id, "done")
            jobs.emit(job_id, {
                "type": "done",
                "message": "Upload complete" + (f" — {uploaded_url}" if uploaded_url else ""),
                "artifacts": result.get("artifacts", {}),
            })
            jobs.schedule_cleanup(job_id)
        except Exception as e:
            jobs.emit(job_id, {
                "type": "stage.error", "stage": "upload",
                "message": str(e), "account_id": account_id,
            })
            jobs.emit(job_id, {"type": "error", "message": str(e)})
            jobs.set_status(job_id, "error")
            jobs.schedule_cleanup(job_id)
        finally:
            _status_mod.info = _orig_info
            _status_mod.success = _orig_success
            _status_mod.warning = _orig_warning

    t = threading.Thread(target=_do_upload, daemon=True)
    t.start()
    return {"uploading": True, "account_id": account_id}


# ---------------------------------------------------------------------------
# 7. Replace _run_pipeline with a dispatcher
# ---------------------------------------------------------------------------

def _run_pipeline(job_id: str, config: dict) -> None:
    from runners import run_short_job, run_long_job, run_recap_job

    def _set_instance(jid, inst):
        with jobs._lock:
            jobs._instances[jid] = inst

    common_kwargs = dict(
        emit=jobs.emit,
        set_status=jobs.set_status,
        set_artifact=jobs.set_artifact,
        get_status=jobs.status,
        set_instance=_set_instance,
        pause_at=jobs.pause_at,
    )

    try:
        cfg_type = config.get("type", "short")
        if cfg_type == "short":
            run_short_job(job_id, config, **common_kwargs)
        elif cfg_type == "long":
            run_long_job(job_id, config, **common_kwargs)
        elif cfg_type == "recap":
            run_recap_job(job_id, config, **common_kwargs)
        else:
            raise ValueError(f"Unknown job type: {cfg_type}")
        jobs.schedule_cleanup(job_id)
    except Exception as e:
        # Print to server stderr so the operator sees the actual cause; the
        # SSE channel only carries the message.
        import traceback
        print(f"[API] Pipeline crashed for job {job_id}:", file=sys.stderr)
        traceback.print_exc()
        jobs.emit(job_id, {
            "type": "error",
            "message": f"{type(e).__name__}: {e}",
        })
        jobs.set_status(job_id, "error")
        jobs.schedule_cleanup(job_id)


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
