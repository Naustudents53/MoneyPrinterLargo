# MoneyPrinter Pro

**Plataforma completa para automatizar la creación, publicación y monitoreo de contenido en YouTube, Twitter/X, marketing de afiliados y outreach local.**

Pensado para correr en local desde una PC: el motor de generación se ejecuta como subprocesos Python aislados y todo se administra desde una webapp moderna construida con FastAPI + React. Ya no necesitas una terminal — abres el navegador, eliges canal, das click y el video se genera, se sube y aparece en tu historial con métricas reales.

---

## Características principales

### 🎬 YouTube — Shorts y videos largos
- **Pipeline completo automático**: tema → guión → metadata → imágenes (AI o stock) → TTS → subtítulos → composición con MoviePy → upload con Selenium.
- **Multi-canal en paralelo**: lanza varios renders al mismo tiempo desde distintos canales, cada uno con su propio perfil de Firefox aislado.
- **Selector de modelo LLM por job**: Gemini 2.5/3 Flash, Gemma 4, Gemini Pro, Ollama (local + cloud: Kimi K2.6, GLM 5.1, Qwen 3.5/3.6, Nemotron, Llama 3.3, DeepSeek), Pollinations.
- **Selector de duración del short** (30s/45s/60s/90s/2min) que mapea a la longitud de guión.
- **Estilos de gancho intercambiables**: 22 hooks curados agrupados en perfiles (educational, storytelling) — random por defecto o fijo para A/B testing.
- **Sugerencias de tema con IA** que lee los últimos 30 temas del canal y propone 5 nuevos sin repetir.
- **Vista previa del script**: genera primero solo el guión (~5s, sin gastar imágenes ni TTS) — lo revisas, lo editas, lo apruebas, y recién ahí corre el render completo.
- **Generación en lote**: cola N shorts de varios canales con un solo click.
- **Sync automático con YouTube** (yt-dlp): tres niveles independientes (subscriber count cada 60 min, stats de videos recientes cada 30 min, sync completo bajo demanda). Catch-up automático al reabrir la app si pasó tiempo offline.

### 🐦 Twitter / X
- Cuentas múltiples con perfil Firefox por cuenta.
- Generación automática de tweets según el topic configurado.
- Posteo con Selenium contra x.com.
- Historial completo.

### 💰 Affiliate Marketing
- Scraping de productos de Amazon con descripción/precio.
- Generación de pitch promocional con LLM.
- Publicación cruzada en Twitter con link de afiliado.

### 📧 Outreach a negocios locales
- Scraping de Google Maps (binario en Go) con filtros por nicho + ubicación.
- Extracción de emails.
- Envío de outreach por SMTP con template HTML.

### ⚙️ Infraestructura
- **Webapp moderna**: dashboard, generación, canales, historial con views/likes/comments, archivos, thumbnails, configuración, panel de jobs en background con progreso en vivo (SSE).
- **Concurrencia segura**: locks de archivo en escrituras al cache JSON, refs por canal para uploads paralelos, cleanup quirúrgico de scratch space.
- **Subprocesos aislados**: cada job de generación corre en su propio proceso Python con su propio perfil Firefox temporal — un crash no tumba a los demás.
- **Backoff exponencial** en el auto-sync cuando YouTube empieza a fallar.

---

## Stack técnico

| Capa | Tecnologías |
|---|---|
| **CLI / motor de pipelines** | Python 3.12, Selenium, MoviePy, ffmpeg, ImageMagick |
| **Backend API** | FastAPI, SSE (Server-Sent Events), asyncio |
| **Frontend** | Vite, React 18, TypeScript, TailwindCSS, Radix UI, lucide-react, sonner |
| **LLMs** | Gemini API, Ollama (local + cloud), Pollinations |
| **Imágenes** | Nano Banana 2 (Gemini), Leonardo AI, Pexels, Pixabay, Wikimedia, Europeana, Library of Congress |
| **TTS** | Edge-TTS, KittenTTS |
| **STT** | local Whisper, AssemblyAI |
| **Scraping** | yt-dlp (YouTube), Go binary (Google Maps) |

---

## Requisitos

- **Python 3.12**
- **Node.js 18+** y **npm**
- **ffmpeg** en el PATH
- **ImageMagick** (necesario para subtítulos con MoviePy)
- **Firefox** con perfil pre-logueado a las plataformas que vas a automatizar
- **Go** (solo si usas el módulo de Outreach con Google Maps)

---

## Instalación

```bash
git clone https://github.com/andrepichardo/MoneyPrinterPro.git
cd MoneyPrinterPro

# Configuración
cp config.example.json config.json
# → edita config.json con tus API keys y rutas

# Entorno virtual + dependencias del motor CLI
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Dependencias de la webapp (backend FastAPI + frontend React)
cd webapp
npm run install:all
```

El comando `npm run install:all` corre `npm install` para el orquestador, `npm --prefix web install` para el frontend, y `pip install -r api/requirements.txt` para el backend.

---

## Uso

### Opción A — Webapp (recomendado)

Desde `webapp/`, con el venv del repo activo:

```bash
npm run dev
```

Esto arranca **backend + frontend en la misma terminal**:
- `[api]` FastAPI con `--reload` en `http://127.0.0.1:8000`
- `[web]` Vite con HMR en `http://127.0.0.1:5173`

Abre `http://127.0.0.1:5173` y todo el flujo está ahí.

### Opción B — CLI clásico

```bash
python src/main.py
```

Menú interactivo en consola — el modo original, útil para debugging y para flujos que aún no están en la webapp (Outreach completo).

### Opción C — Job aislado por línea de comando

```bash
# Genera y sube un short al canal X
python webapp/api/run_job.py generate --channel-id <uuid> --kind short --upload

# Genera un video largo de una serie
python webapp/api/run_job.py generate --channel-id <uuid> --kind long --series-id un_dia_en_la_historia

# Sube el último .mp4 generado de un canal
python webapp/api/run_job.py upload-last --channel-id <uuid>

# Tweet
python webapp/api/run_job.py tweet --account-id <uuid>
```

---

## Estructura del proyecto

```
MoneyPrinterPro/
├── src/                          Motor de pipelines (Python)
│   ├── main.py                   CLI interactivo
│   ├── cron.py                   Runner headless (legacy)
│   ├── config.py                 Lectura de config.json
│   ├── cache.py                  Persistencia .mp/*.json + file locks
│   ├── llm_provider.py           Gemini / Ollama / Pollinations dispatch
│   ├── classes/
│   │   ├── YouTube.py            Pipeline completo shorts + longs
│   │   ├── Twitter.py            Selenium x.com
│   │   ├── AFM.py                Affiliate Marketing
│   │   ├── Outreach.py           Google Maps + SMTP
│   │   └── Tts.py                Edge-TTS / KittenTTS
│   └── ...
├── webapp/
│   ├── api/
│   │   ├── main.py               FastAPI + lifespan auto-sync
│   │   ├── run_job.py            Driver de subprocesos
│   │   ├── auto_sync.py          Scheduler de 3 tiers
│   │   └── requirements.txt
│   ├── web/                      Vite + React + TS
│   │   └── src/
│   │       ├── pages/            Dashboard, Generate, Channels, ChannelDetail, ...
│   │       ├── components/       UI primitives + dialogs + paneles
│   │       └── lib/api.ts        Cliente API
│   └── README.md                 Doc de la webapp
├── scripts/
│   ├── sync_youtube_cache.py     Sync con YouTube (yt-dlp)
│   ├── make_thumbnail.py         Generador de thumbnails
│   └── ...
├── docs/                         Documentación adicional por módulo
├── .mp/                          Scratch space + cache JSON (gitignored)
├── config.example.json
├── config.json                   (gitignored)
└── requirements.txt
```

---

## Configuración

Toda la configuración vive en `config.json` en la raíz. Las claves principales:

| Sección | Claves |
|---|---|
| **Core** | `verbose`, `headless`, `firefox_profile`, `imagemagick_path`, `threads` |
| **Render** | `short_render_profile`, `short_render_fps`, `short_ken_burns`, `short_karaoke_subtitles`, `short_crossfade_seconds`, `render_codec`, `render_preset` |
| **LLM** | `llm_provider`, `gemini_models`, `gemini_api_key`, `ollama_base_url`, `ollama_model`, `pollinations_text_model` |
| **TTS / STT** | `tts_provider`, `tts_voice`, `stt_provider`, `whisper_model`, `assembly_ai_api_key` |
| **Imágenes** | `leonardo_api_key`, `pexels_api_key`, `pixabay_api_key`, `europeana_api_key`, `hf_api_key` |
| **Series (largos)** | `series` con `id`, `title_template`, `script_brief`, `section_themes`, `thumbnail_overlay` |
| **Auto-sync** | `auto_sync.enabled`, `*_interval_minutes`, `*_enabled`, `recent_video_count` |

El editor de configuración en la webapp (Settings) cubre todas las claves no-secretas con UI agrupada. Las API keys también se pueden editar ahí con toggle "mostrar/ocultar secrets".

Ver [`config.example.json`](config.example.json) para un template completo, y [`docs/Configuration.md`](docs/Configuration.md) para detalles por clave.

---

## Auto-sync de estadísticas

La webapp corre un scheduler en background que actualiza views/likes/suscriptores sin que tengas que darle a "Sync YT" manual:

| Tier | Intervalo default | Qué hace |
|---|---|---|
| **Light** | 60 min | Subscriber count por canal (1 request por canal, ~5s total) |
| **Recent** | 30 min | Stats de los N (default 10) videos más recientes por canal |
| **Full** | 12 h *(off)* | Sync completo equivalente al botón manual |

Todo configurable desde Settings → Auto-sync, con toggles, intervalos editables, ejecución forzada, logs por tier y backoff automático si YouTube empieza a fallar.

Cuando cierras la app y la vuelves a abrir, cada tier hace **catch-up** inteligente: si pasó más tiempo que el intervalo, corre casi de inmediato; si pasó menos, espera solo el tiempo restante del ciclo original.

---

## Notas de seguridad

- El proyecto **no maneja autenticación** — está pensado para uso local en tu propia máquina.
- Los uploads usan **Selenium contra YouTube Studio** (no la API oficial). Necesitas un perfil de Firefox pre-logueado.
- El sync con YouTube usa **yt-dlp** que scrapea la página pública — no requiere API key pero está sujeto a rate limits invisibles.
- Las API keys viven en `config.json` (gitignored). Nunca commitearlo.

---

## Disclaimer

Este proyecto es para uso personal y educativo. Yo, como autor, no me hago responsable de ningún uso indebido. Cumple los términos de servicio de las plataformas (YouTube, X/Twitter, Amazon, etc.) que estés automatizando — la automatización agresiva puede resultar en suspensión de tu cuenta.

---

## Autor

**André Pichardo** — [@andrepichardo](https://github.com/andrepichardo)

Proyecto personal, mantenido por mí.

---

## Créditos

Este proyecto está basado originalmente en [MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2) de [FujiwaraChoki](https://github.com/FujiwaraChoki), bajo licencia AGPL v3. La versión actual ha sido reescrita y extendida significativamente: nueva webapp completa (FastAPI + React), pipeline rediseñado para correr varios canales en paralelo de forma segura, sistema de auto-sync, multi-provider de LLMs (Gemini + Ollama cloud/local + Pollinations), vista previa de script, generación en lote, y muchas otras features que no estaban en el original. Gracias al autor original por la base.
