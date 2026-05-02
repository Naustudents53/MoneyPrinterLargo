# MoneyPrinter Pro

Webapp completa estilo CRM para administrar todo MoneyPrinterV2 desde el navegador:
canales de YouTube, cuentas Twitter/X, generación de shorts y videos largos con
**progreso en vivo**, series, configuración, y más.

![arquitectura](https://img.shields.io/badge/stack-FastAPI%20+%20React%2018%20+%20Vite%20+%20Tailwind-emerald)

## Stack

- **Backend**: FastAPI + SSE streaming (envuelve el código existente en `src/`).
- **Frontend**: Vite + React 18 + TypeScript + Tailwind v3 + Radix UI + lucide-react + sonner.
- **Branding**: gradient esmeralda → cian → violeta, con acento dorado. Modo dark/light/system.

## Estructura

```
webapp/
├── api/                    FastAPI backend
│   ├── main.py             Endpoints REST + SSE
│   ├── run_job.py          Driver de subprocesos (generación, upload, tweet)
│   └── requirements.txt
├── web/                    Frontend Vite + React
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/     UI primitives (button, card, dialog, etc.)
│   │   ├── pages/          Dashboard, Channels, ChannelDetail, Generate, ...
│   │   ├── lib/api.ts      Cliente del backend
│   │   └── index.css       Tema dark/light + paleta de marca
│   └── ...
├── start.bat               Lanza ambos servicios (Windows)
├── start.sh                Lanza ambos servicios (macOS/Linux)
└── README.md
```

## Setup (primera vez)

Desde la raíz del proyecto, con el venv de MoneyPrinterV2 activado:

```powershell
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

Luego, una sola línea instala todo (backend + frontend + orquestador):

```bash
cd webapp
npm run install:all
```

Esto ejecuta:
- `npm install` (orquestador con `concurrently`)
- `npm --prefix web install` (frontend Vite + React)
- `pip install -r api/requirements.txt` (FastAPI)

## Ejecutar (una sola terminal de VS Code)

Desde `webapp/`:

```bash
npm run dev
```

Esto arranca **backend + frontend en la misma terminal** con logs prefijados:
- `[api]` → FastAPI con `--reload` en `http://127.0.0.1:8000`
- `[web]` → Vite con HMR en `http://127.0.0.1:5173`

Abre **http://127.0.0.1:5173**. Los dos procesos comparten la terminal pero conservan su hot-reload independiente. `Ctrl+C` mata ambos.

### Variantes

```bash
# Desde la raíz del repo (sin cd)
npm --prefix webapp run dev

# Solo el backend
npm run dev:api

# Solo el frontend
npm run dev:web

# Build de producción del frontend
npm run build
```

### Scripts legacy (también disponibles)

```bash
# Windows — abre dos ventanas de cmd separadas
webapp\start.bat

# macOS/Linux equivalente
bash webapp/start.sh
```

## Funcionalidades

| Página | Lo que puedes hacer |
|---|---|
| **Dashboard** | Stats globales (canales, videos, archivos), videos recientes, atajos. |
| **Generar** | Lanzar generación de shorts o longs con tema personalizado, modo de imagen, serie, auto-upload. **Progreso en vivo** vía SSE — los logs del CLI aparecen en un terminal embebido. |
| **Canales YouTube** | CRUD: crear, editar, eliminar canales. Cards con voces, niche, image style, conteo de videos. |
| **Detalle de canal** | Listado completo de videos del historial, búsqueda, eliminar individual o vaciar todo, subir el último generado, editar el canal. |
| **Twitter / X** | CRUD de cuentas, postear con un click (con progreso), historial de tweets. |
| **Series** | Visualización de las series configuradas en `config.json` (title template, thumbnail overlay, script brief, secciones). |
| **Configuración** | Editor visual de `config.json` agrupado por sección (Core, LLM, Imagen, Audio, Twitter). Toggle para mostrar secrets. |
| **Archivos de video** | Listar `.mp4` cacheados en `.mp/`, eliminar individual o vaciar todo. |
| **Affiliate** | Listar productos vinculados a cuentas Twitter. |
| **Outreach** | Stub — el flujo completo se ejecuta desde el CLI por ahora. |

## Cómo funciona el progreso en vivo

Las acciones largas (generar, subir, postear) son procesos pesados (Selenium,
MoviePy, ffmpeg) que pueden tardar minutos. Para verlas en vivo:

1. El frontend abre un `EventSource` contra un endpoint SSE del backend.
2. El backend lanza un subproceso (`webapp/api/run_job.py`) con stdout
   line-buffered.
3. Cada línea de stdout se reenvía como evento `log` SSE al navegador.
4. El componente `ProgressDialog` muestra los logs en un terminal embebido con
   colores tipo CLI, tiempo transcurrido, y status badge.

Si cierras el modal mientras el job corre, el subprocess **sigue ejecutándose**
hasta terminar — solo se desconecta el stream en el cliente.

## Notas de integración con MoneyPrinterV2

- Reutiliza `src/cache.py` para leer/escribir `.mp/youtube.json`,
  `.mp/twitter.json`, `.mp/afm.json`.
- Lee `config.json` directamente y usa los getters de `src/config.py`.
- El driver de subprocesos (`run_job.py`) reutiliza `classes/YouTube.py`,
  `classes/Twitter.py`, `classes/Tts.py`, `llm_provider.py`.
- No reimplementa lógica de pipeline — solo expone una capa REST/SSE.

## Personalización

- **Colores de marca**: edita las variables `--brand-start`, `--brand-mid`,
  `--brand-end` en [web/src/index.css](web/src/index.css).
- **Endpoint del backend en producción**: define `VITE_API_BASE` antes de
  `npm run build`.
- **Puerto del backend**: cambia el target en [web/vite.config.ts](web/vite.config.ts)
  si lo mueves.

## Limitaciones conocidas

- El usuario debe tener el venv del proyecto principal activo y dependencias
  de MoneyPrinterV2 instaladas (Selenium, MoviePy, ffmpeg, ImageMagick).
- Outreach corre en proceso largo y aún no expone progreso por SSE.
- El programa no maneja autenticación — pensado para uso local.
- Subir/eliminar videos fuera de YouTube Studio (la API de YouTube real)
  requiere OAuth y no está integrado: se usa Selenium contra YouTube Studio.
