# Design Brief — MoneyPrinter Largo (Webapp)

> Documento auto-contenido para enviar a Claude Design. No requiere acceso al
> repo: tiene producto, sistema actual, mapa de pantallas, dolencias y
> objetivos de rediseño. **Idioma de la UI: español.**

---

## 1. ¿Qué es el producto?

**MoneyPrinter Largo** es un *content studio* local para creadores que automatiza
4 flujos:

1. **YouTube Shorts y Long videos** — generación end-to-end: tema → guion (LLM
   Ollama) → narración (KittenTTS) → imágenes (Nano Banana 2 / fotos stock) →
   composición (MoviePy) → subida (Selenium contra YouTube Studio).
2. **Twitter / X** — generación y publicación de tweets via Selenium.
3. **Affiliate Marketing** — scraping de Amazon → pitch con LLM → publica en X.
4. **Outreach Local** — scraping de Google Maps → extracción de emails → envío
   de outreach por SMTP.

La webapp es la **capa visual** sobre el CLI: FastAPI envuelve los módulos
existentes y expone REST + SSE; el frontend consume todo.

**Audiencia:** un solo usuario / creador, en su máquina local. Usa la app
varios minutos al día para lanzar jobs largos (2–25 min) y revisar resultados.

**Tono de marca:** *"Imprime largo, edita poco."* — estudio de creador,
profesional, con energía. Mezcla CRM + DAW + cuaderno editorial.

---

## 2. Stack técnico (restricciones)

- **Frontend:** Vite + React 18 + TypeScript + **Tailwind v3** + **Radix UI**
  + **lucide-react** (iconos) + **sonner** (toasts) + react-router.
- **Componentes UI:** estilo shadcn/ui (Card, Button, Dialog, Tabs, Select,
  Switch, Badge, Input, Textarea, Label, Skeleton, EmptyState, DropdownMenu).
- **Sin shadcn pesado de Charts.** Si se necesitan, se pueden añadir.
- **Modo dark / light / system** (toggle en header). El dark es el principal
  porque el usuario lo usa de noche.
- **Backend:** FastAPI + SSE para progreso en vivo de jobs largos. Esto es
  central: muchas vistas están conectadas a streams.
- **Fuentes:** Inter (sans), Sora (display), JetBrains Mono (mono).

---

## 3. Sistema de diseño actual

### 3.1 Paleta — variables CSS HSL

**Light theme** (canvas cálido, tinta negra, acentos eléctricos):

```css
--background: 42 43% 96%;          /* canvas crema */
--foreground: 222 31% 13%;         /* tinta */
--card: 0 0% 100%;
--primary: 183 82% 36%;            /* cyan profundo */
--accent: 14 88% 58%;              /* naranja vivo */
--success: 149 70% 34%;
--warning: 39 92% 52%;
--gold: 43 91% 50%;
--rose: 337 78% 62%;
--destructive: 0 78% 55%;
--border: 220 18% 83%;
--muted: 220 18% 91%;
```

**Dark theme** (tinta profunda, acentos eléctricos):

```css
--background: 224 39% 6%;
--foreground: 43 32% 94%;
--card: 224 34% 10%;
--primary: 181 92% 50%;            /* cyan eléctrico */
--accent: 14 94% 66%;              /* coral */
--success: 151 72% 47%;
--gold: 43 96% 60%;
--border: 224 20% 22%;
```

### 3.2 Gradiente de marca

```css
--brand-start: 183 90% 42%;   /* cyan */
--brand-mid:   14 92% 60%;    /* naranja-coral */
--brand-end:   75 86% 44%;    /* lima */
--brand-deep:  252 58% 38%;   /* violeta */

.brand-text {
  background: linear-gradient(120deg,
    hsl(var(--brand-start)),
    hsl(var(--brand-mid)) 55%,
    hsl(var(--brand-end))
  );
  -webkit-background-clip: text;
  color: transparent;
}
```

Hay también `--brand-gradient` (CSS bg-image) para botones y heros.

### 3.3 Tipografía

- **Display (Sora)** — títulos, números grandes, hero. Tracking apretado.
- **Sans (Inter)** — UI body, controles. Features `cv11`, `ss01` activadas.
- **Mono (JetBrains Mono)** — eyebrows, versión, snippets, terminales.

```css
.eyebrow {
  font-family: mono;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.24em;
  color: hsl(var(--primary));
}
```

### 3.4 Superficies y profundidad

- `--radius: 0.625rem` (10px) — radio base, modular.
- **`.studio-surface`** — `border-border/70 bg-card/80 backdrop-blur-xl
  shadow-[0_18px_60px_-44px_hsl(var(--foreground)/.45)]`.
- **`.studio-hover`** — `-translate-y-0.5` + glow sutil con primary.
- **`.glass`** — fallback para overlays.
- **`.glow-ring`** — ring + drop-shadow doble (primary + accent).
- **`.mesh-bg`** — fondo sutil con grid 42×42 + 2 washes diagonales.
- **`.grain`** — overlay de ruido (opacity 0.03, mix-blend overlay).

### 3.5 Botones (variantes)

`default | brand | destructive | outline | secondary | ghost | link | soft`.
Todas con `hover:-translate-y-0.5` y `active:scale-[.98]`. La variante `brand`
es un gradiente cyan→coral→lima que se usa como CTA principal.

Sizes: `sm (h-8) | default (h-9) | lg (h-11) | xl (h-12) | icon (9×9)`.

---

## 4. Mapa de pantallas

Layout: **sidebar fija (256 px) + header sticky (64 px) + área principal con
`mesh-bg`**. Max width del contenido: `96rem`.

### Sidebar (4 grupos)

```
PRINCIPAL
  · Dashboard           (LayoutDashboard)
  · Generar contenido   (Sparkles)
CANALES
  · Canales YouTube     (Youtube)
  · Cuentas Twitter / X (Twitter)
  · Series              (BookOpen)
OTROS FLUJOS
  · Affiliate Marketing (ShoppingBag)
  · Outreach Local      (Mail)
  · Archivos de video   (Film)
  · Thumbnails          (Image)
SISTEMA
  · Operaciones         (Activity)
  · Configuración       (Settings)
```

Footer del sidebar: versión `v1.0.0` + tag `MPL` mono, y la frase de marca
"Imprime largo, edita poco." en gradiente.

### Header global

`title + description + eyebrow opcional` a la izquierda. A la derecha:

- `actions` slot (CTA contextual de cada página)
- **BackgroundJobs** (chip con jobs corriendo en background)
- **Sistema** dropdown — badge online/offline + info del backend (versión,
  LLM, STT, voz TTS, aspect ratio, headless).
- **Tema** dropdown (Sun / Moon / Monitor).
- **GitHub** icon link.

### Páginas

| Página | Propósito | Contenido principal |
|---|---|---|
| **Dashboard** (`/`) | Snapshot general | Hero editorial con gradiente, 4 StatCards (Canales / Cuentas / Productos / Storage), lista de "Videos recientes", panel "Atajos". |
| **Generar** (`/generate`) | Lanzar job de video | Form 2 columnas: izquierda (canal, kind tabs short/long, tema, duración 60/120/180 s, fuente imágenes ai/fotos, serie, switch auto-upload, switch preview-at-end, CTA brand), derecha (resumen del canal, tips, image_style). Abre `ProgressDialog` con SSE en vivo. |
| **Canales YouTube** (`/channels`) | CRUD canales | Grid de cards: nickname, niche, voces, image style, count de videos. Botón "Nuevo canal" abre dialog. |
| **Detalle canal** (`/channels/:id`) | Lista de videos del canal | Header con eyebrow "Canal", videos en lista filtrable, acciones (subir el último, vaciar todo, editar). |
| **Twitter / X** (`/twitter`) | CRUD cuentas + post | Lista cuentas, botón "Postear" lanza ProgressDialog. Historial de tweets. |
| **Series** (`/series`) | Plantillas de long video | Cards de series desde `config.json` (title template, thumbnail overlay, brief, secciones). Solo lectura. |
| **Configuración** (`/settings`) | Editor visual de `config.json` | Tabs por sección (Core, LLM, Imagen, Audio, Twitter). Toggle "mostrar secrets". Inputs / selects mapeados a getters. |
| **Archivos de video** (`/storage`) | Gestión de `.mp/*.mp4` | Tabla con nombre, tamaño, fecha. Eliminar individual / vaciar todo. |
| **Thumbnails** (`/thumbnails`) | Listado de PNGs | Grid de previews. |
| **Affiliate** (`/affiliate`) | Productos vinculados | Tabla productos × cuenta X. |
| **Outreach** (`/outreach`) | Stub | Placeholder con CTA "Ejecutar desde CLI". |
| **Operaciones** (`/operations`) | Jobs corriendo | Lista de jobs SSE activos, status, tiempo, log mini. |

### Componentes especiales

- **ProgressDialog** — modal grande con terminal embebido (fondo oscuro, fuente
  mono, colores ANSI light), badge de status (running / done / error), tiempo
  transcurrido, botón "Cancelar" / "Cerrar". Es el corazón de la UX porque los
  jobs son largos.
- **StatCard** — `studio-surface` + top rule de 3px en color semántico (primary
  / accent / gold / success), wash radial en esquina top-right, eyebrow + valor
  display + hint, icon a la derecha.
- **EmptyState** — icono + título + descripción + CTA. Muy usado.
- **BackgroundJobs** — popover con jobs activos miniaturizados.
- **ConfirmDialog** — destructivo para eliminar canales / videos.

---

## 5. Lo que queremos del rediseño

### 5.1 Mantener (esto ya funciona)

- ✅ Identidad de marca: gradiente cyan → coral → lima → violeta.
- ✅ Dual theme dark/light, dark como principal.
- ✅ Layout sidebar fija + header sticky + mesh-bg.
- ✅ Sora display + Inter body + Mono mono.
- ✅ Eyebrows mono uppercase con tracking ancho.
- ✅ Estructura de info (sidebar 4 grupos, páginas listadas).
- ✅ Stack: Tailwind + Radix + lucide. **No cambiar de framework.**
- ✅ Texto en español.

### 5.2 Mejorar / repensar

1. **Hero del Dashboard** — actualmente es funcional pero plano. Buscar
   composición editorial más fuerte: tipografía mixta, ritmo vertical, tal vez
   un gráfico ambiente o un widget de "última actividad" más visual.

2. **StatCards** — son sólidas pero todas igual. ¿Distinción visual cuando un
   stat tiene tendencia? Sparklines, mini-gráficos, deltas semana a semana.

3. **Generar (página crítica)** — es la pantalla más usada. La forma actual
   funciona, pero se siente como "form CRM". Buscar algo más cercano a un
   *control panel de DAW / mesa de mezcla*: bloques claros para INPUT (canal,
   tema), TRANSFORM (formato, duración, fuente imágenes), OUTPUT (auto-upload,
   preview). El CTA brand merece más jerarquía.

4. **ProgressDialog** — el terminal embebido es plano. Idea: dividirlo en
   *etapas* (script → TTS → imágenes → render → upload), cada una con su propio
   progreso, y un panel "log raw" colapsable. Que el usuario vea **dónde está**
   no solo un stream de líneas.

5. **Canales (lista)** — cards de canales pueden ganar miniaturas / color por
   canal / preview del último video. Sentirse menos a "tabla con CSS" y más a
   "rack de canales".

6. **Settings** — el editor de `config.json` por tabs es ok pero denso. Repensar
   la densidad: los grupos son ~30 campos, mucho input apilado. Tal vez
   cards colapsables, o una columna izquierda con secciones + columna derecha
   con campos del grupo activo.

7. **Empty states** — actualmente texto + icono + CTA. Pueden ser más
   *evocativos* (ilustración monocroma vectorial coherente con el brand).

8. **Microinteracciones** — añadir "feel" sin caer en exceso: transiciones
   en cambio de tab, focus rings con glow primary, toasts con tipografía
   display, skeleton shimmer ya existente, loading states más ricos en jobs
   largos.

9. **Densidad** — la app vive en pantalla amplia (desktop). En 1440 px o más,
   el contenido se siente disperso. Considerar layout de **2–3 columnas** en
   pantallas anchas para Dashboard y Generate (sidebar de contexto + main +
   panel de detalle/inspector).

10. **Background jobs (chip header)** — actualmente es discreto. Si hay 2+ jobs
    corriendo, el usuario quiere ver el progreso sin abrir cada modal. Idea:
    barra delgada bajo el header con jobs activos cuando hay > 0.

### 5.3 Restricciones de implementación

- **No introducir libs nuevas pesadas** (chart libs, animation libs grandes).
  Si necesitas charts, framer-motion u otros, márcalo y justifica.
- **Mantener accesibilidad Radix** (focus rings, ARIA labels, keyboard nav).
- **No mover archivos**, mantener la estructura `webapp/web/src/{components,pages,lib}`.
- **Tokens primero**: cualquier color/sombra nuevo debe entrar como variable
  CSS en `index.css` y mapeo en `tailwind.config.js`. No hardcodear hex.
- **Mobile no es prioridad** — el target es desktop ≥ 1280 px. Pero no romper
  ≥ 1024 px (donde el sidebar todavía se muestra).

---

## 6. Entregables esperados

Idealmente, la entrega del rediseño debería incluir:

1. **Hero Dashboard rediseñado** — JSX completo (Tailwind classes) listo para
   pegar.
2. **Generate page** — layout panel-de-control completo.
3. **ProgressDialog** — versión por etapas + log raw.
4. **StatCard v2** — variante con sparkline / delta.
5. **Channels grid** — card de canal con miniatura + meta.
6. **Tokens nuevos** — cualquier color/sombra/radius extra, en formato
   variables CSS HSL.
7. **Notas de rationale corto** por componente (1–2 frases del *por qué*).

No hace falta entregarlo todo en una sola pasada; iteraciones son bienvenidas.

---

## 7. Inspiración / referencia

- **Linear** — densidad, jerarquía, eyebrows, atajos visibles.
- **Vercel dashboard** — superficies card, gradientes sutiles, dark.
- **Raycast** — comando central, microinteracciones limpias.
- **Ableton Live / Logic** — para Generate como mesa de mezcla.
- **Stripe dashboard** — tabs de settings, densidad de form.

Lo que **no** queremos:

- ❌ Estilo "AI app genérica" con purpura saturado y gradientes glow everywhere.
- ❌ Cards rounded-3xl gigantes con padding excesivo.
- ❌ Sombras infladas / efectos glassmorphism overdone.
- ❌ Pictogramas estilo 3D / claymorphism.

---

## 8. Resumen ejecutivo (TL;DR para el diseñador)

> Soy MoneyPrinter Largo, una app local de creador que orquesta 4 flujos
> automatizados (YouTube, Twitter, Affiliate, Outreach). Tengo un sistema base
> sólido en Tailwind + Radix con paleta cyan/coral/lima/violeta, dual theme,
> superficies "studio" con grid sutil y tipografía Sora/Inter/Mono. Quiero que
> mi UI suba un escalón: que el Dashboard se sienta editorial, que Generate se
> sienta como un control panel profesional, que ProgressDialog muestre etapas
> claras del pipeline, y que las pantallas densas (Settings, Channels) ganen
> ritmo visual sin perder eficiencia. Mantén stack y tokens; mejora composición,
> microinteracciones y narrativa visual.
