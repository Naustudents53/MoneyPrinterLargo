# MoneyPrinter Largo

Plataforma local para crear, renderizar, publicar y monitorear contenido automatizado en YouTube, Twitter/X, marketing de afiliados y outreach.

Este proyecto fue desarrollado y mantenido por **Daniel Lopez**. Esta versión, su integración local, la webapp y los flujos actuales corresponden a Daniel Lopez.

---

## Qué hace

MoneyPrinter Largo combina un motor Python con una webapp moderna para manejar el flujo completo de creación de contenido desde una sola máquina:

- Generación de shorts y videos largos para YouTube.
- Creación de guiones, metadata, imágenes, voz, subtítulos y render final.
- Upload automatizado usando perfiles locales de Firefox.
- Dashboard web para canales, historial, archivos, métricas y jobs en vivo.
- Publicación en Twitter/X con cuentas separadas.
- Flujos de marketing de afiliados.
- Outreach a negocios locales con scraping, extracción de emails y envío SMTP.
- Sincronización de métricas de YouTube usando `yt-dlp`.

La idea es simple: configurar tus proveedores, abrir la app, elegir el canal o flujo y dejar que el sistema ejecute el pipeline.

---

## Características principales

### YouTube

- Pipeline completo: tema, guion, metadata, imágenes, TTS, subtítulos, composición con MoviePy y subida con Selenium.
- Soporte para shorts y videos largos.
- Vista previa de guion antes de renderizar.
- Generación por lotes.
- Manejo de canales con configuración propia.
- Multi-provider para LLMs e imágenes.
- Historial local de videos, archivos y métricas.
- Auto-sync de suscriptores, views, likes y comentarios.

### Webapp

- Backend con FastAPI.
- Frontend con React, TypeScript, Vite y TailwindCSS.
- Progreso en vivo de jobs largos mediante SSE.
- Paneles para Dashboard, Generar, Canales, Series, Twitter/X, Affiliate, Outreach, Storage, Thumbnails, Operations y Settings.
- Configuración visual de `config.json`.

### Twitter/X

- Múltiples cuentas.
- Generación automática de tweets.
- Publicación con Selenium.
- Historial local por cuenta.

### Affiliate Marketing

- Scraping de productos.
- Generación de copy promocional con LLM.
- Publicación cruzada en Twitter/X.

### Outreach

- Scraping de negocios locales.
- Extracción de emails.
- Envío de correos por SMTP usando plantillas.

---

## Stack técnico

| Área | Tecnologías |
|---|---|
| Motor principal | Python 3.12 |
| Automatización | Selenium, Firefox profiles |
| Video | MoviePy, ffmpeg, ImageMagick |
| Backend | FastAPI, asyncio, SSE |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Radix UI, lucide-react |
| LLMs | Gemini, Ollama, Pollinations |
| TTS | Edge-TTS, KittenTTS |
| STT | Whisper local, AssemblyAI |
| Scraping / sync | yt-dlp, scripts locales, binario Go para Google Maps |

---

## Requisitos

- Python 3.12
- Node.js 18+ y pnpm 10.16+
- Firefox
- ffmpeg disponible en el PATH
- ImageMagick
- Git Bash, WSL o terminal compatible para ejecutar scripts `.sh` en Windows
- Go solo si vas a usar el flujo completo de Outreach con Google Maps

También necesitas las API keys o servicios locales que vayas a usar, por ejemplo Gemini, Ollama, Pexels, Pixabay, Leonardo, AssemblyAI, SMTP, etc.

---

## Instalación rápida

Desde la raíz del proyecto:

```bash
bash scripts/setup_local.sh
```

Ese script:

- Crea `config.json` desde `config.example.json` si todavía no existe.
- Crea el entorno virtual `venv`.
- Instala dependencias Python.
- Ajusta algunos defaults locales.
- Ejecuta el preflight local.

Luego instala la webapp:

```bash
source venv/bin/activate
cd webapp
pnpm run install:all
```

En Windows PowerShell, activa el entorno con:

```powershell
.\venv\Scripts\Activate.ps1
```

---

## Configuración

El archivo principal de configuración es:

```text
config.json
```

Empieza desde:

```text
config.example.json
```

Configura, como mínimo:

- `firefox_profile`: perfil de Firefox ya logueado en YouTube/X.
- `imagemagick_path`: ruta de ImageMagick si no está en el PATH.
- `llm_provider`: proveedor de texto.
- API keys necesarias según el proveedor elegido.
- Proveedor de imágenes.
- Proveedor de TTS/STT.
- Canales, voces, estilos y series si vas a generar videos largos.

Más detalles en [`docs/Configuration.md`](docs/Configuration.md).

Importante: `config.json` es local y puede contener secretos. No subas API keys ni rutas privadas.

---

## Ejecutar la webapp

Desde `webapp/`, con el entorno virtual activo:

```bash
pnpm run dev
```

Esto levanta dos servicios en la misma terminal:

- API FastAPI: `http://127.0.0.1:8000`
- Frontend Vite: `http://127.0.0.1:5173`

Abre:

```text
http://127.0.0.1:5173
```

También puedes ejecutarlo desde la raíz:

```bash
pnpm --dir webapp run dev
```

---

## Ejecutar por CLI

Para usar el modo clásico por terminal:

```bash
python src/main.py
```

Para validar configuración local:

```bash
python scripts/preflight_local.py
```

Para ejecutar jobs específicos:

```bash
# Generar y subir un short
python webapp/api/run_job.py generate --channel-id <uuid> --kind short --upload

# Generar un video largo
python webapp/api/run_job.py generate --channel-id <uuid> --kind long --series-id <series_id>

# Subir el último video generado de un canal
python webapp/api/run_job.py upload-last --channel-id <uuid>

# Publicar tweet
python webapp/api/run_job.py tweet --account-id <uuid>
```

---

## Estructura del proyecto

```text
MoneyPrinterLargo-public/
├── src/                       Motor principal en Python
│   ├── main.py                CLI interactivo
│   ├── config.py              Lectura de config.json
│   ├── cache.py               Persistencia local en .mp/
│   ├── llm_provider.py        Dispatch Gemini / Ollama / Pollinations
│   └── classes/
│       ├── YouTube.py         Pipeline de videos
│       ├── Twitter.py         Automatización de X/Twitter
│       ├── AFM.py             Affiliate Marketing
│       ├── Outreach.py        Outreach local
│       └── Tts.py             Voces y TTS
├── webapp/
│   ├── api/                   Backend FastAPI
│   │   ├── main.py            Endpoints REST + SSE
│   │   ├── run_job.py         Runner de jobs aislados
│   │   └── auto_sync.py       Scheduler de métricas
│   └── web/                   Frontend React + Vite
│       └── src/
│           ├── pages/         Pantallas de la app
│           ├── components/    Componentes UI
│           └── lib/api.ts     Cliente API
├── scripts/                   Setup, preflight, sync y helpers
├── docs/                      Documentación técnica
├── assets/                    Recursos estáticos
├── fonts/                     Fuentes usadas en renders
├── .mp/                       Cache local y scratch space
├── config.example.json        Plantilla de configuración
├── requirements.txt           Dependencias del motor Python
└── run_webapp.py              Helper para lanzar la app
```

---

## Flujo recomendado

1. Ejecuta `bash scripts/setup_local.sh`.
2. Edita `config.json`.
3. Activa el entorno virtual.
4. Instala la webapp con `cd webapp && pnpm run install:all`.
5. Corre `python scripts/preflight_local.py`.
6. Inicia la webapp con `pnpm run dev`.
7. Abre `http://127.0.0.1:5173`.
8. Crea o revisa tus canales.
9. Genera un guion de prueba.
10. Renderiza y sube cuando todo esté correcto.

---

## Notas de seguridad

- Este proyecto está pensado para uso local.
- No incluye autenticación de usuarios en la webapp.
- Los uploads usan Selenium contra YouTube Studio, no la API oficial de YouTube.
- El sync con YouTube usa `yt-dlp` sobre páginas públicas.
- Las plataformas pueden aplicar rate limits o restricciones.
- Automatizar contenido o publicaciones puede incumplir términos de servicio si se usa de forma agresiva.
- No publiques `config.json`, perfiles de navegador, tokens, cookies ni API keys.

---

## Autor

**Daniel Lopez**

Desarrollo, integración y mantenimiento de esta versión de MoneyPrinter Largo.

---

## Participantes

Perfiles que participaron o aparecen vinculados al historial/base del proyecto:

- [@Naustudents53](https://github.com/Naustudents53) - Daniel Lopez, autor y mantenedor de esta versión.
- [@andrepichardo](https://github.com/andrepichardo) - aportes/base previa del proyecto.
- [@FujiwaraChoki](https://github.com/FujiwaraChoki) - base original MoneyPrinterV2.
- [@AdityaKhowalGithub](https://github.com/AdityaKhowalGithub)
- [@cool-aid](https://github.com/cool-aid)
- [@FedeGioz](https://github.com/FedeGioz)
- [@TomyDiNero](https://github.com/TomyDiNero)
- [@Xeno852](https://github.com/Xeno852)

---

## Créditos

Este proyecto toma inspiración y parte de la idea original de proyectos tipo MoneyPrinter, incluyendo MoneyPrinterV2 de FujiwaraChoki. Esta versión fue adaptada, extendida y reestructurada por **Daniel Lopez** con webapp, integración local, flujos de generación, automatización y herramientas adicionales.

---

## Disclaimer

Este software se entrega para fines personales, educativos y de automatización local. El autor no se hace responsable por usos indebidos, spam, incumplimiento de términos de servicio, suspensión de cuentas o problemas derivados del uso de automatización en plataformas externas.
