"""Production orchestrator — coordinates the full pipeline."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from .models import (
    ProductionProject, Phase, ProductionMode, ShotStatus,
    ShotVersion, RetryStrategy, _uid, _now,
)
from .storage import ProjectStorage, get_storage

log = logging.getLogger(__name__)


class CancelledError(Exception):
    pass


class ProductionOrchestrator:
    def __init__(self, storage: ProjectStorage | None = None,
                 on_event: Callable[[str, dict], None] | None = None):
        self._storage = storage or get_storage()
        self._on_event = on_event or (lambda t, d: None)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _emit(self, event_type: str, data: dict | None = None):
        self._on_event(event_type, data or {})

    def _save(self, project: ProductionProject):
        self._storage.save_project(project)

    def _check_cancelled(self):
        if self._cancelled:
            raise CancelledError("Production cancelled")

    def run_production(self, project: ProductionProject) -> ProductionProject:
        self._cancelled = False
        self._emit("project_created", {"project_id": project.id, "title": project.config.title})
        phase_seq = self._get_phase_sequence(project.config.production_mode)

        start_from = 0
        phase_values = [p.value for p, _ in phase_seq]
        if project.phase.value in phase_values:
            start_from = phase_values.index(project.phase.value)

        for i in range(start_from, len(phase_seq)):
            phase, handler = phase_seq[i]
            self._check_cancelled()
            project.phase = phase
            project.progress = (i / len(phase_seq)) * 100
            project.updated_at = _now()
            self._save(project)
            self._emit("phase_started", {"phase": phase.value, "progress": project.progress})
            try:
                project = handler(project)
                self._save(project)
                self._emit("phase_completed", {"phase": phase.value})
            except CancelledError:
                project.phase = Phase.CANCELLED
                self._save(project)
                return project
            except Exception as e:
                log.error("Phase %s failed: %s", phase.value, e, exc_info=True)
                project.error = f"Phase {phase.value}: {e}"
                project.phase = Phase.FAILED
                self._save(project)
                self._emit("phase_failed", {"phase": phase.value, "error": str(e)})
                return project

        project.phase = Phase.COMPLETED
        project.progress = 100
        self._save(project)
        self._storage.save_version(project)
        self._emit("project_completed", {"project_id": project.id})
        return project

    def _phase_init(self, p): p.logs.append(f"[{_now():.0f}] Init: {p.config.title or p.config.topic}"); return p
    def _phase_topic(self, p): p.logs.append(f"[{_now():.0f}] Topic: {p.config.topic}"); return p

    def _phase_research(self, p):
        from .script_engine import generate_research
        return generate_research(p)

    def _phase_concept(self, p):
        from .script_engine import generate_concept
        return generate_concept(p)

    def _phase_narrative(self, p): return p

    def _phase_script(self, p):
        from .script_engine import generate_script
        return generate_script(p)

    def _phase_segmentation(self, p): return p

    def _phase_visual_bible(self, p):
        from .visual_bible import generate_visual_bible
        return generate_visual_bible(p)

    def _phase_char_bible(self, p):
        from .visual_bible import generate_character_bible
        return generate_character_bible(p)

    def _phase_env_bible(self, p):
        from .visual_bible import generate_location_bible
        return generate_location_bible(p)

    def _phase_storyboard(self, p):
        from .storyboard import generate_storyboard
        return generate_storyboard(p)

    def _phase_shot_planning(self, p):
        from .shot_planner import assign_models
        from .rhythm import analyze_rhythm
        return analyze_rhythm(assign_models(p))

    def _phase_prompts(self, p):
        from .prompt_director import generate_prompts
        from .prompt_critic import critique_prompts
        return critique_prompts(generate_prompts(p))

    def _phase_refs(self, p): return p

    def _phase_generation(self, p):
        if p.config.dry_run or p.config.production_mode in (ProductionMode.PLAN, ProductionMode.PLAN_PROMPTS):
            for shot in p.shots:
                if shot.status == ShotStatus.PLANNED:
                    shot.status = ShotStatus.APPROVED
                    shot.versions.append(ShotVersion(
                        version=1, prompt_used=shot.optimized_prompt or shot.prompt,
                        model_used=shot.model_id or "dry-run",
                        provider_job_id=f"dry-run-{shot.id}", cost=0, generated_at=_now()))
            return p
        return self._run_generation(p)

    def _run_generation(self, project):
        from .shot_planner import get_generation_batches
        from .cost import check_budget, record_cost
        for batch in get_generation_batches(project):
            self._check_cancelled()
            for shot_id in batch:
                self._check_cancelled()
                shot = next((s for s in project.shots if s.id == shot_id), None)
                if not shot or shot.status in (ShotStatus.APPROVED, ShotStatus.SKIPPED):
                    continue
                budget = check_budget(project, shot.estimated_cost or 0)
                if not budget["allowed"]:
                    self._emit("budget_exceeded", budget)
                    project.phase = Phase.PAUSED
                    self._save(project)
                    return project
                shot.status = ShotStatus.GENERATING
                self._emit("shot_started", {"shot_id": shot.id, "sequence": shot.sequence})
                try:
                    self._generate_shot(project, shot)
                    shot.status = ShotStatus.QC_PENDING
                    self._emit("shot_completed", {"shot_id": shot.id})
                except Exception as e:
                    log.error("Shot %s failed: %s", shot.id, e)
                    shot.status = ShotStatus.FAILED
                    self._emit("shot_failed", {"shot_id": shot.id, "error": str(e)})
                self._save(project)
        return project

    def _generate_shot(self, project, shot):
        import asyncio as _aio
        from video_providers import get_provider
        from video_providers.base import GenerationRequest
        config = {}
        try:
            import sys, os
            root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
            with open(os.path.join(root, "config.json"), encoding="utf-8") as f:
                config = json.load(f).get("higgsfield", {})
        except Exception:
            pass
        provider = get_provider(project.config.provider, config=config)
        req = GenerationRequest(
            prompt=shot.optimized_prompt or shot.prompt,
            negative_prompt=shot.negative_prompt,
            duration_sec=shot.duration_sec,
            aspect_ratio=project.config.aspect_ratio,
            resolution=project.config.resolution,
            model_id=shot.model_id,
            reference_images=shot.reference_assets)

        loop = asyncio.new_event_loop()
        try:
            async def _go():
                r = await provider.generate(req)
                r = await provider.wait_for_job(r.job_id)
                if r.output_url or r.output_path:
                    import sys, os
                    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
                    dest = Path(root) / ".mp" / "higgsfield" / "shots" / project.id
                    await provider.download_output(r.job_id, dest)
                    r.output_path = str(dest / f"{r.job_id}.mp4")
                return r
            result = loop.run_until_complete(_go())
        finally:
            loop.close()

        v = ShotVersion(
            version=len(shot.versions) + 1, file_path=result.output_path or "",
            prompt_used=req.prompt, model_used=result.model_id,
            provider_job_id=result.job_id, cost=result.cost, generated_at=_now())
        shot.versions.append(v)
        shot.selected_version = v.version
        if result.cost is not None:
            from .cost import record_cost
            record_cost(project, shot.id, provider.name, result.model_id, shot.estimated_cost, result.cost)
        return {"job_id": result.job_id}

    def _phase_qc(self, p):
        from .qc import run_qc_pass
        run_qc_pass(p)
        return p

    def _phase_regen(self, p):
        if p.config.dry_run:
            return p
        from .qc import evaluate_shot, select_retry_strategy
        for shot in p.shots:
            if shot.status != ShotStatus.REJECTED or shot.regeneration_count >= shot.max_regenerations:
                if shot.status == ShotStatus.REJECTED:
                    shot.status = ShotStatus.FAILED
                continue
            strategy = select_retry_strategy(shot, shot.versions[-1].qc if shot.versions and shot.versions[-1].qc else None)
            shot.regeneration_count += 1
            shot.status = ShotStatus.REGENERATING
            self._emit("shot_regeneration", {"shot_id": shot.id, "attempt": shot.regeneration_count, "strategy": strategy.value})
            if strategy == RetryStrategy.REWRITE:
                from .prompt_director import generate_single_prompt
                shot.optimized_prompt = generate_single_prompt(shot, p)
            elif strategy == RetryStrategy.SIMPLIFY:
                shot.optimized_prompt = re.sub(r'\([^)]*\)', '', shot.optimized_prompt or shot.prompt).strip()
                words = shot.optimized_prompt.split()
                if len(words) > 150:
                    shot.optimized_prompt = " ".join(words[:150])
            elif strategy == RetryStrategy.DIFFERENT_MODEL:
                shot.model_id = "fast-motion-2" if shot.model_id != "fast-motion-2" else "cinematic-studio-3"
            try:
                self._generate_shot(p, shot)
                shot.status = ShotStatus.QC_PENDING
                evaluate_shot(p, shot)
            except Exception as e:
                shot.status = ShotStatus.FAILED
                log.error("Regen failed shot %s: %s", shot.id, e)
            self._save(p)
        return p

    def _phase_audio(self, p):
        if p.config.dry_run:
            return p
        from .audio import produce_audio
        return produce_audio(p)

    def _phase_assembly(self, p):
        if p.config.dry_run:
            return p
        from .renderer import render_final
        return render_final(p)

    def _phase_final_qc(self, p):
        from .qc import final_quality_gate
        r = final_quality_gate(p)
        if not r["passed"] and not p.config.dry_run:
            p.logs.append(f"Final QC issues: {r['issues']}")
        return p

    def _phase_metadata(self, p):
        from .metadata import generate_metadata
        return generate_metadata(p)

    def _phase_thumbnail(self, p): return p

    def _phase_publishing(self, p):
        from .manifest import generate_manifest
        return generate_manifest(p)

    def _get_phase_sequence(self, mode):
        full = [
            (Phase.INIT, self._phase_init), (Phase.TOPIC_ANALYSIS, self._phase_topic),
            (Phase.RESEARCH, self._phase_research), (Phase.CONCEPT, self._phase_concept),
            (Phase.NARRATIVE, self._phase_narrative), (Phase.SCRIPT, self._phase_script),
            (Phase.SEGMENTATION, self._phase_segmentation),
            (Phase.VISUAL_BIBLE, self._phase_visual_bible),
            (Phase.CHARACTER_BIBLE, self._phase_char_bible),
            (Phase.ENVIRONMENT_BIBLE, self._phase_env_bible),
            (Phase.STORYBOARD, self._phase_storyboard),
            (Phase.SHOT_PLANNING, self._phase_shot_planning),
            (Phase.PROMPT_ENGINEERING, self._phase_prompts),
            (Phase.REFERENCE_PREP, self._phase_refs),
            (Phase.GENERATION, self._phase_generation),
            (Phase.VIDEO_QC, self._phase_qc),
            (Phase.REGENERATION, self._phase_regen),
            (Phase.AUDIO, self._phase_audio),
            (Phase.ASSEMBLY, self._phase_assembly),
            (Phase.FINAL_QC, self._phase_final_qc),
            (Phase.METADATA, self._phase_metadata),
            (Phase.THUMBNAIL, self._phase_thumbnail),
            (Phase.PUBLISHING, self._phase_publishing),
        ]
        if mode == ProductionMode.PLAN:
            return full[:13]
        elif mode == ProductionMode.PLAN_PROMPTS:
            return full[:14]
        elif mode == ProductionMode.RENDER_ONLY:
            return [(Phase.ASSEMBLY, self._phase_assembly), (Phase.FINAL_QC, self._phase_final_qc),
                    (Phase.METADATA, self._phase_metadata), (Phase.PUBLISHING, self._phase_publishing)]
        elif mode == ProductionMode.REGENERATE_FAILED:
            return [(Phase.REGENERATION, self._phase_regen), (Phase.VIDEO_QC, self._phase_qc)]
        elif mode == ProductionMode.UPGRADE:
            return [(Phase.GENERATION, self._phase_generation), (Phase.VIDEO_QC, self._phase_qc),
                    (Phase.REGENERATION, self._phase_regen)]
        return full
