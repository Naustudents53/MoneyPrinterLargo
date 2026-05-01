# Next.js 16 Dashboard — Studio

This is a **Next.js 16.2.4 App Router** dashboard using Turbopack. Breaking APIs exist — check `node_modules/next/dist/docs/` before writing unfamiliar code.

## Key Architecture Facts

### Tech Stack
- **React 19.2**, **Next.js 16** (Turbopack), **Tailwind CSS 4**, **Radix UI**, **Framer Motion**, **Zustand** state management

### Tailwind v4 / CSS
- Design tokens are defined in `src/app/globals.css` via `@theme inline { ... }` — do NOT use `tailwind.config.ts`
- Custom colors: `surface-base`, `surface-raised`, `surface-overlay`, `surface-sunken`, `border-*`, `text-*`, `accent-purple`, `accent-blue`
- Custom shadows: `shadow-glow-purple`, `shadow-glow-blue`
- Font variables come from Next.js font loader, mapped to `--font-sans` / `--font-mono` in `@theme inline`

### Component Architecture
```
src/
  app/
    layout.tsx          # Root layout with font loading, globals.css import
    page.tsx            # Renders <StudioShell />
    globals.css         # Tailwind v4 entry + theme tokens + scrollbar
  components/
    shell/              # Layout: Sidebar, TopBar, ContextPanel, FloatingAIDirector, CommandPalette, StudioShell
    studio/             # Domain: ProductionStepper, StudioCard, ProductionCanvas, all 7 Stage* components
    ui/                 # Primitives: tooltip, dialog, scroll-area (Radix wrappers)
  stores/
    project.ts          # Zustand — projects, steps, scenes, clips, script, timeline, export
    agents.ts           # AI agent statuses + job queue
    ui.ts               # Panel visibility, sidebar state, command palette
  lib/utils.ts          # cn() helper (clsx + tailwind-merge)
```

### Layout Structure
- `<StudioShell>` renders the full app: Sidebar (collapsible, 60px/240px) + TopBar + ProductionCanvas + ContextPanel + FloatingAIDirector + CommandPalette
- The canvas is dynamic per stage (7 steps), switched via `<AnimatePresence mode="wait">`
- **All components must be `"use client"`** — the shell uses browser APIs (window, crypto, framer-motion)

### Data Flow
- Production state is in Zustand (`useProjectStore`) — NOT fetched from an API
- Stages populate data via `useEffect` with sample data (scripts, scenes, clips) — replace with real RPC when backend is wired
- The `onComplete` callback auto-advances stages in the ProductionCanvas

### API Backend
- `api_server.py` runs at `http://localhost:8000` — scrapes YouTube Studio via Selenium
- `StageSelectMovie` fetches `GET /api/youtube/videos` on mount; falls back to hardcoded data on error
- Start the API *before* the frontend if real video data is needed

### Framer Motion Conventions
- Page/stage transitions: `<AnimatePresence mode="wait">` with `x` slide + opacity
- Cards: `whileHover={{ y: -4 }}`, `whileTap={{ scale: 0.98 }}` 
- Active nav indicator: `layoutId="activeNav"` for shared layout animations
- Loading spinners: `animate={{ rotate: 360 }}` with `repeat: Infinity`

### Gotchas
- `lucide-react` icon names: check before use — "Youtube" doesn't exist, use "Video" instead
- Use `crypto.randomUUID()` for IDs (available in browser, not Node 19 default)
- The `cn()` helper MUST be used on all dynamic className combinations
- No `console.log` in production paths — the linter will flag it
