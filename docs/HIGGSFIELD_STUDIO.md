# Higgsfield Long Video Studio

Cinematic long-form video production pipeline for MoneyPrinterLargo. Transforms a topic into a fully produced video through a 23-phase automated pipeline that handles research, scriptwriting, storyboarding, visual consistency bibles, AI video generation, quality control, audio narration, and final assembly.

## Quick Start

### 1. Configure

Add the `higgsfield` section to your `config.json` (see [Configuration Reference](HIGGSFIELD_CONFIGURATION.md)):

```json
{
  "higgsfield": {
    "enabled": true,
    "api_key": "your-higgsfield-api-key",
    "default_quality": "quality",
    "budget_limit": 50.0
  }
}
```

### 2. Create a Production

**Via the Web UI:** Navigate to `/higgsfield` and click "New Production". Fill in the topic, genre, quality mode, and other settings.

**Via the API:**

```bash
curl -X POST http://localhost:8000/api/higgsfield/projects \
  -H "Content-Type: application/json" \
  -d '{"topic": "The history of the Silk Road", "genre": "history", "quality": "quality"}'
```

### 3. Run the Pipeline

```bash
# SSE stream of pipeline events
curl http://localhost:8000/api/higgsfield/projects/{project_id}/run
```

## The 23-Phase Pipeline

| # | Phase | Description |
|---|-------|-------------|
| 1 | `init` | Initialize project structure and validate configuration |
| 2 | `topic_analysis` | Analyze the topic for angles, scope, and audience |
| 3 | `research` | LLM-driven research on the topic (light or deep mode) |
| 4 | `concept` | Generate the creative concept and narrative approach |
| 5 | `narrative` | Define narrative arc and emotional beats |
| 6 | `script` | Generate full narration script with chapter structure |
| 7 | `segmentation` | Break script into narration blocks with timing |
| 8 | `visual_bible` | Establish visual style: camera, lighting, color grade |
| 9 | `character_bible` | Define consistent character appearances |
| 10 | `environment_bible` | Define consistent location/environment looks |
| 11 | `storyboard` | Create scene-by-scene visual plan |
| 12 | `shot_planning` | Plan individual shots with types, durations, model routing |
| 13 | `prompt_engineering` | Generate cinematic video generation prompts (15 director rules) |
| 14 | `reference_prep` | Prepare reference images/frames for generation |
| 15 | `generation` | Submit shots to the video generation provider |
| 16 | `video_qc` | Score generated shots against quality thresholds |
| 17 | `regeneration` | Re-generate shots that failed QC (up to max attempts) |
| 18 | `audio` | Generate TTS narration via edge-tts |
| 19 | `assembly` | FFmpeg assembly of shots + audio into final video |
| 20 | `final_qc` | Final quality pass on the assembled video |
| 21 | `metadata` | Generate YouTube title, description, tags |
| 22 | `thumbnail` | Generate video thumbnail |
| 23 | `publishing` | Upload to YouTube (if auto_upload enabled) |

## Production Modes

| Mode | What it does |
|------|-------------|
| `plan` | Run through research, concept, and script only. No generation. |
| `plan_prompts` | Plan through prompt engineering. Lets you review prompts before spending money. |
| `full` | Complete pipeline from topic to published video. |
| `upgrade` | Re-run generation and assembly on an existing project with higher quality settings. |
| `regenerate_failed` | Only re-generate shots that previously failed QC. |
| `render_only` | Skip generation, assemble from existing approved shots. |

## Director Modes

- **`auto`** -- The pipeline runs end-to-end without human intervention. Shots are auto-approved if they pass the QC threshold.
- **`director`** -- The pipeline pauses at key decision points (after script, after storyboard, after each shot generation) and waits for manual approval via the API or UI.

## Quality Modes

| Mode | QC Threshold | Use Case |
|------|-------------|----------|
| `budget` | 50 | Fast drafts, prototyping. Accepts lower-quality shots. |
| `balanced` | 65 | Good enough for most content. Reasonable cost. |
| `quality` | 75 | High-quality output. Default setting. |
| `cinema` | 85 | Maximum quality. More regenerations, higher cost. |

Quality mode also influences model selection in the shot planner -- higher quality modes prefer more capable (and expensive) models.

## Dry Run Mode

Set `dry_run: true` in the project config or `config.json` to test the entire pipeline without making real API calls to the video generation provider. The pipeline runs all phases, generates prompts, and simulates generation results. Useful for validating scripts, prompts, and cost estimates before spending money.

## Genre Styles

17 built-in genre presets, each defining visual tone, camera style, lighting, and color grade:

`documentary`, `true_crime`, `science`, `history`, `mystery`, `horror`, `space`, `technology`, `nature`, `cinematic_essay`, `travel`, `sports`, `business`, `fiction`, `explainer`, `war`, `architecture`

Each genre preset is applied during prompt engineering to ensure visual consistency. Example (`documentary`):
- Visual tone: cinematic realism with documentary gravitas
- Camera: steady, observational, motivated movement
- Lighting: natural, motivated, atmospheric
- Color grade: desaturated earth tones, deep shadows, warm highlights

## Budget System

- Set a `budget_limit` per project (in USD)
- Per-shot cost estimation before generation
- Real-time cost tracking via `cost_events` table
- Pipeline stops if budget would be exceeded
- View cost breakdown via `GET /api/higgsfield/projects/{id}/cost`

## Resumability

The pipeline saves state after every phase. If the process stops (crash, cancellation, or manual pause), restart it with `GET /api/higgsfield/projects/{id}/run` and it resumes from the last completed phase.

## API Endpoints

All endpoints are under `/api/higgsfield`.

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects` | List all projects |
| `POST` | `/projects` | Create a new production |
| `GET` | `/projects/{id}` | Get project details |
| `DELETE` | `/projects/{id}` | Delete a project |
| `GET` | `/projects/{id}/run` | Start/resume pipeline (SSE stream) |
| `POST` | `/projects/{id}/cancel` | Cancel a running pipeline |

### Project Components

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{id}/script` | Get script, narration blocks, chapters |
| `GET` | `/projects/{id}/storyboard` | Get scenes and chapters |
| `GET` | `/projects/{id}/shots` | Get all shots |
| `POST` | `/projects/{id}/shots/{shot_id}` | Shot action (approve/reject/regenerate/edit_prompt) |
| `GET` | `/projects/{id}/visual-bible` | Get visual bible, characters, locations |
| `GET` | `/projects/{id}/timeline` | Get timeline summary |
| `GET` | `/projects/{id}/cost` | Get cost summary and estimates |
| `PUT` | `/projects/{id}/budget` | Update budget limit |
| `GET` | `/projects/{id}/versions` | List project versions |
| `GET` | `/projects/{id}/manifest` | Get production manifest |
| `GET` | `/projects/{id}/rhythm` | Get visual rhythm metrics and warnings |

### Providers & Learning

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/providers` | List available video providers |
| `GET` | `/providers/{name}/models` | List models for a provider |
| `GET` | `/prompt-memory` | Get best-performing prompts |
| `GET` | `/learning` | Get learning statistics |
| `GET` | `/genres` | List available genre styles |

## Frontend

The web UI is accessible at `/higgsfield` and consists of three pages:

- **Studio** (`/higgsfield`) -- Project list and overview
- **New Production** (`/higgsfield/new`) -- Create a new production with all options
- **Project View** (`/higgsfield/project/{id}`) -- Monitor pipeline progress, review shots, manage budget
