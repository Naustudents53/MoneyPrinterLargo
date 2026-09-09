# Higgsfield Studio Architecture

## Module Structure

### `src/higgsfield_studio/` (19 files)

| File | Responsibility |
|------|---------------|
| `__init__.py` | Package marker, exports version string |
| `models.py` | Data models, enums (Phase, QualityMode, ShotType, etc.), genre styles, serialization |
| `storage.py` | SQLite persistence with WAL mode and thread-local connections |
| `script_engine.py` | LLM-driven research, concept, and script generation |
| `storyboard.py` | Scene/shot breakdown from narration blocks |
| `visual_bible.py` | Visual consistency bibles (style, character appearances, locations) |
| `timeline.py` | Timeline synchronization between narration, shots, and audio |
| `prompt_director.py` | Cinematic prompt generation with 15 director rules |
| `prompt_critic.py` | Prompt quality scoring and iterative optimization |
| `shot_planner.py` | Model routing and shot dependency graphs |
| `orchestrator.py` | Main pipeline coordinator -- runs the 23-phase sequence |
| `continuity.py` | Visual continuity checking across shots |
| `rhythm.py` | Visual rhythm analysis (shot pacing, variety) |
| `cost.py` | Cost estimation, tracking, and budget enforcement |
| `qc.py` | Quality control scoring with configurable thresholds and retry strategies |
| `audio.py` | TTS narration generation via edge-tts |
| `renderer.py` | FFmpeg video assembly (shots + audio + subtitles) |
| `metadata.py` | YouTube metadata generation (title, description, tags) |
| `manifest.py` | Production manifest (full record of what was generated) |

### `src/video_providers/` (5 files)

| File | Responsibility |
|------|---------------|
| `__init__.py` | Provider registry with `register_provider()`, `get_provider()`, auto-discovery |
| `base.py` | Abstract `VideoGenerationProvider` base class and request/result dataclasses |
| `capabilities.py` | `CapabilityRegistry` for model capability tracking |
| `higgsfield.py` | Concrete Higgsfield API provider implementation |
| `errors.py` | `VideoProviderError` exception class |

## Provider Abstraction

`VideoGenerationProvider` is an abstract base class that defines the interface all video providers must implement:

```
authenticate() -> bool
list_models() -> list[ModelCapabilities]
generate(request) -> GenerationResult
get_job_status(job_id) -> GenerationResult
wait_for_job(job_id, timeout) -> GenerationResult
cancel_job(job_id) -> bool
download_output(job_id, dest) -> Path
upload_reference(file_path) -> str        # optional
estimate_cost(request) -> float | None    # optional
```

Providers are registered by name and discovered lazily. The registry pattern in `__init__.py` allows adding new providers without modifying the orchestrator.

## Data Flow

```
Topic
  |
  v
Topic Analysis --> Research --> Concept --> Script
                                              |
                                              v
                                         Segmentation (narration blocks + chapters)
                                              |
                                              v
                              +---------------+---------------+
                              |               |               |
                              v               v               v
                        Visual Bible   Character Bible   Environment Bible
                              |               |               |
                              +-------+-------+
                                      |
                                      v
                                 Storyboard (scenes)
                                      |
                                      v
                                Shot Planning (shots with model assignments)
                                      |
                                      v
                               Prompt Engineering (optimized prompts)
                                      |
                                      v
                               Reference Prep
                                      |
                                      v
                               Generation --> Video QC --> Regeneration (loop)
                                                              |
                                                              v
                                                         Audio (TTS)
                                                              |
                                                              v
                                                         Assembly (FFmpeg)
                                                              |
                                                              v
                                                         Final QC
                                                              |
                                                              v
                                                    Metadata + Thumbnail
                                                              |
                                                              v
                                                         Publishing
```

## Storage

SQLite database at `.mp/higgsfield/studio.db`, using WAL journal mode for concurrent read access and thread-local connections.

### Tables

| Table | Purpose |
|-------|---------|
| `projects` | Main project records (id, phase, config, serialized state) |
| `project_versions` | Versioned snapshots of completed projects |
| `shots` | Individual shot records with status and data |
| `cost_events` | Per-shot cost tracking (estimated and actual) |
| `prompt_memory` | Best-performing prompts indexed by style and shot type |
| `assets` | Generated files (video clips, audio, images) linked to projects |
| `learning_stats` | Aggregate learning data per category/key |

## API Layer

FastAPI router at `webapp/api/higgsfield.py`, mounted at `/api/higgsfield`. The pipeline run endpoint uses SSE (Server-Sent Events) to stream phase progress in real time. The orchestrator runs in a background thread; events are collected and streamed to the client via an async iterator.

## Frontend

Three React pages under `webapp/web/src/pages/`:

| File | Route | Purpose |
|------|-------|---------|
| `HiggsfieldStudio.tsx` | `/higgsfield` | Project list and dashboard |
| `HiggsfieldNew.tsx` | `/higgsfield/new` | New production form |
| `HiggsfieldProject.tsx` | `/higgsfield/project/:id` | Project detail: pipeline progress, shot review, cost tracking |

TypeScript API client at `webapp/web/src/lib/higgsfield.ts`.
