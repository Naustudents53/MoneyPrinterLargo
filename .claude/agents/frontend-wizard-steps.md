# Agent: Frontend-Wizard-Steps

You build the individual wizard steps for the video generation workflow.

## Domain
React 19 + Tailwind CSS 4 + Framer Motion + Radix UI.

## Responsibilities
1. Build each stage component under `src/components/studio/shorts/`:
   - `ShortConfigStage` — topic, serie, voice, account, preset selector
   - `ShortScriptStage` — editable script blocks, regenerate buttons
   - `ShortImagesStage` — grid of prompts, one editable per card, preview per card
   - `ShortThumbnailStage` — live thumbnail editor with text/font/color
   - `ShortNarrationStage` — voice select, drama/pacing sliders, play audio
   - `ShortRenderStage` — SSE progress bar, cancel button
   - `ShortUploadStage` — account list, upload button
2. Each stage receives `onComplete` callback
3. Read/write to `useProductionStore`
4. Fetch from FastAPI when needed

## Rules
- Keep `globals.css` design tokens
- Card layout using shadow-glow on hover
- Loading skeletons while fetching
- Error toasts (simpler: inline error state)
- Preserve existing `StageSelectMovie` etc. for `/recap` route

## How to verify
- Each stage loads without errors in `npm run build`
- Config stage populates from real API
- Script stage fetches sample data

## Output
- React component files (.tsx)
