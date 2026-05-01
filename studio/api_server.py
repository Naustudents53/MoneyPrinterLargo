"""
Backend API server for MoneyPrinter Studio.

Provides:
  - YouTube Studio scraping (existing)
  - Health checks (existing)
  - Config read-only endpoints (series, voices, accounts)
  - Preset CRUD
  - Job lifecycle + SSE streaming for async pipeline steps
  - TTS preview endpoint
"""

import json
import os
import sys
import time
import uuid
import threading
import random
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="MoneyPrinter Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
# job manager (in-memory)
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = {}
        self._clients = {}
        self._status = {}
        self._results = {}

    def create(self):
        job_id = str(uuid.uuid4())
        with self._lock:
            self._events[job_id] = []
            self._clients[job_id] = []
            self._status[job_id] = "queued"
            self._results[job_id] = {}
        return job_id

    def emit(self, job_id, event):
        with self._lock:
            if job_id not in self._events:
                return
            self._events[job_id].append(event)
            for client_queue in self._clients.get(job_id, []):
                client_queue.append(event)

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

    def cancel(self, job_id):
        with self._lock:
            if job_id not in self._status:
                return False
            if self._status[job_id] in ("done", "error"):
                return False
            self._status[job_id] = "cancelled"
        self.emit(job_id, {"type": "cancel", "message": "Job cancelled by user"})
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
# Config inference
# ---------------------------------------------------------------------------

def _infer_voices():
    voice = "Jasper"
    try:
        sys.path.insert(0, ROOT_DIR)
        from src.config import get_tts_voice
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
        "Pablo":    {"id": "es-ES-AlvaroNeural",     "alias": "Pablo",   "lang": "es", "gender": "male"},
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
        accounts.append({
            "id": a.get("id"),
            "nickname": a.get("nickname", "Unknown"),
            "niche": a.get("niche", ""),
            "language": a.get("language", ""),
            "image_style": a.get("image_style", ""),
            "short_voice": a.get("short_voice", ""),
            "long_voice": a.get("long_voice", ""),
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


@app.get("/api/health")
def health_check():
    fp = _get_firefox_profile()
    has_profile = bool(fp and os.path.isdir(fp))
    return {
        "status": "ok",
        "version": "2.0.0",
        "firefox_profile_ready": has_profile,
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


# --- Jobs ------------------------------------------------------------------

@app.post("/api/jobs")
def create_job(data: dict):
    job_id = jobs.create()
    jobs.set_result(job_id, {
        "type": data.get("type", "short"),
        "account_id": data.get("account_id"),
        "topic": data.get("topic", ""),
        "series_id": data.get("series_id"),
        "image_mode": data.get("image_mode", "ai"),
        "preset_id": data.get("preset_id"),
    })
    jobs.emit(job_id, {"type": "queued", "message": "Job queued", "job_id": job_id})
    result = jobs.get_result(job_id)
    thread = threading.Thread(target=_run_pipeline, args=(job_id, result), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    result = jobs.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": jobs.status(job_id), "config": result}


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    return jobs.stream(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    ok = jobs.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot cancel this job")
    return {"cancelled": True}


# --- TTS -------------------------------------------------------------------

@app.post("/api/tts/preview")
def tts_preview(data: dict):
    text = data.get("text", "")
    voice_id = data.get("voice_id", "es-ES-AlvaroNeural")
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    try:
        sys.path.insert(0, ROOT_DIR)
        from src.classes.Tts import TTS
        tts = TTS()
        preview_path = os.path.join(CACHE_DIR, f"preview_{int(time.time())}.wav")
        tts.synthesize(text[:150], output_file=preview_path, voice_id=voice_id)
        return {"path": preview_path, "duration_seconds": 5}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Pipeline simulation
# ---------------------------------------------------------------------------

def _run_pipeline(job_id: str, config: dict) -> None:
    """Run a simulated pipeline that emits SSE events."""
    stages = [
        ("script", 3, "Generating script..."),
        ("images", 12, "Generating images ({current}/{total})..."),
        ("thumbnail", 1, "Generating thumbnail..."),
        ("tts", 1, "Generating narration..."),
        ("render", 5, "Rendering video ({current}/{total})..."),
    ]

    for stage, total, template in stages:
        if jobs.status(job_id) == "cancelled":
            return

        jobs.set_status(job_id, "running")
        for current in range(1, total + 1):
            if jobs.status(job_id) == "cancelled":
                return
            message = template.format(current=current, total=total)
            jobs.emit(job_id, {
                "type": "progress",
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
                "percent": int((current / total) * 100),
            })
            time.sleep(random.uniform(0.3, 1.0))

    jobs.set_status(job_id, "done")
    jobs.emit(job_id, {
        "type": "done",
        "message": "Pipeline complete",
        "video_path": f".mp/{job_id}_final.mp4",
    })


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
