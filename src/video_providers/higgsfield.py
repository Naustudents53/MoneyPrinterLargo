"""Higgsfield video generation provider."""
from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .base import (
    VideoGenerationProvider, GenerationRequest, GenerationResult,
    JobStatus, ModelCapabilities, QualityMode,
)
from .errors import (
    AuthenticationError, GenerationError, NetworkError,
    RateLimitError, PolicyError, ModelNotAvailableError,
)
from .capabilities import CapabilityRegistry

log = logging.getLogger(__name__)


def _read_hf_config() -> dict:
    """Read higgsfield config section."""
    import sys, os
    root = os.path.dirname(sys.path[0]) if sys.path[0] else os.getcwd()
    cfg_path = os.path.join(root, "config.json")
    try:
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("higgsfield", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class HiggsfieldProvider(VideoGenerationProvider):
    """Higgsfield AI video generation provider."""

    def __init__(self, config: dict | None = None, capability_registry: CapabilityRegistry | None = None):
        self._config = config or _read_hf_config()
        self._api_key = self._config.get("api_key", "")
        self._base_url = self._config.get("api_url", "https://api.higgsfield.ai/v1")
        self._client: httpx.AsyncClient | None = None
        self._authenticated = False
        self._dry_run = self._config.get("dry_run", False)
        self._registry = capability_registry

    @property
    def name(self) -> str:
        return "higgsfield"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=httpx.Timeout(30.0, read=120.0),
            )
        return self._client

    async def authenticate(self) -> bool:
        if self._dry_run:
            self._authenticated = True
            return True
        if not self._api_key:
            raise AuthenticationError("No Higgsfield API key configured", provider=self.name)
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            if resp.status_code == 401:
                raise AuthenticationError("Invalid Higgsfield API key", provider=self.name)
            resp.raise_for_status()
            self._authenticated = True
            return True
        except httpx.HTTPError as e:
            raise NetworkError(f"Cannot reach Higgsfield API: {e}", provider=self.name)

    async def list_models(self) -> list[ModelCapabilities]:
        if self._dry_run:
            return self._mock_models()
        if self._registry:
            cached = self._registry.get(self.name)
            if cached:
                return cached.models
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            resp.raise_for_status()
            raw_models = resp.json()
            models = self._parse_models(raw_models)
            if self._registry:
                from .capabilities import ProviderCapabilities
                self._registry.store(ProviderCapabilities(provider=self.name, models=models))
            return models
        except httpx.HTTPError as e:
            log.warning("Failed to fetch Higgsfield models: %s", e)
            if self._registry:
                cached = self._registry.get(self.name)
                if cached:
                    return cached.models
            return self._mock_models()

    def _parse_models(self, raw: Any) -> list[ModelCapabilities]:
        models = []
        items = raw if isinstance(raw, list) else raw.get("models", raw.get("data", []))
        for item in items:
            if isinstance(item, dict):
                model_id = item.get("id", item.get("model_id", str(uuid.uuid4())))
                models.append(ModelCapabilities(
                    model_id=model_id,
                    name=item.get("name", model_id),
                    max_duration_sec=float(item.get("max_duration", item.get("max_duration_sec", 10))),
                    min_duration_sec=float(item.get("min_duration", item.get("min_duration_sec", 2))),
                    supported_aspect_ratios=item.get("aspect_ratios", item.get("supported_aspect_ratios", ["16:9"])),
                    supported_resolutions=item.get("resolutions", item.get("supported_resolutions", ["1080p"])),
                    supports_audio=bool(item.get("audio", item.get("supports_audio", False))),
                    supports_references=bool(item.get("references", item.get("supports_references", False))),
                    supports_multi_shot=bool(item.get("multi_shot", item.get("supports_multi_shot", False))),
                    supports_start_frame=bool(item.get("start_frame", item.get("supports_start_frame", False))),
                    supports_end_frame=bool(item.get("end_frame", item.get("supports_end_frame", False))),
                    supports_video_reference=bool(item.get("video_reference", item.get("supports_video_reference", False))),
                    estimated_cost_per_second=item.get("cost_per_second", item.get("estimated_cost_per_second")),
                    tags=item.get("tags", []),
                ))
        return models or self._mock_models()

    def _mock_models(self) -> list[ModelCapabilities]:
        return [
            ModelCapabilities(
                model_id="cinematic-studio-3",
                name="Cinematic Studio 3.0",
                max_duration_sec=10,
                min_duration_sec=2,
                supported_aspect_ratios=["16:9", "21:9", "9:16", "1:1"],
                supported_resolutions=["720p", "1080p"],
                supports_references=True,
                supports_start_frame=True,
                supports_end_frame=True,
                quality_tier=QualityMode.CINEMA,
                tags=["cinematic", "hero", "establishing"],
            ),
            ModelCapabilities(
                model_id="fast-motion-2",
                name="Fast Motion 2.0",
                max_duration_sec=8,
                min_duration_sec=2,
                supported_aspect_ratios=["16:9", "9:16"],
                supported_resolutions=["720p", "1080p"],
                supports_references=True,
                quality_tier=QualityMode.BALANCED,
                tags=["action", "dynamic", "fast"],
            ),
            ModelCapabilities(
                model_id="draft-1",
                name="Draft 1.0",
                max_duration_sec=10,
                min_duration_sec=2,
                supported_aspect_ratios=["16:9"],
                supported_resolutions=["720p"],
                quality_tier=QualityMode.BUDGET,
                tags=["draft", "preview", "transition"],
            ),
        ]

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        if self._dry_run:
            return self._mock_generate(request)
        try:
            client = await self._get_client()
            body: dict[str, Any] = {
                "prompt": request.prompt,
                "duration": request.duration_sec,
                "aspect_ratio": request.aspect_ratio,
                "resolution": request.resolution,
            }
            if request.model_id:
                body["model"] = request.model_id
            if request.negative_prompt:
                body["negative_prompt"] = request.negative_prompt
            if request.reference_images:
                body["reference_images"] = request.reference_images
            if request.start_frame:
                body["start_frame"] = request.start_frame
            if request.end_frame:
                body["end_frame"] = request.end_frame
            if request.seed is not None:
                body["seed"] = request.seed

            resp = await client.post("/generate", json=body)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                raise RateLimitError(
                    "Rate limited by Higgsfield",
                    provider=self.name,
                    retry_after_sec=float(retry_after) if retry_after else None,
                )
            if resp.status_code == 403:
                raise PolicyError(resp.text, provider=self.name)
            resp.raise_for_status()
            data = resp.json()
            return GenerationResult(
                job_id=data.get("id", data.get("job_id", str(uuid.uuid4()))),
                status=JobStatus.QUEUED,
                provider=self.name,
                model_id=request.model_id or data.get("model", "unknown"),
                metadata={"request": body},
            )
        except httpx.HTTPError as e:
            raise NetworkError(f"Higgsfield API error: {e}", provider=self.name)

    def _mock_generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            job_id=f"dry-run-{uuid.uuid4().hex[:12]}",
            status=JobStatus.COMPLETED,
            provider=self.name,
            model_id=request.model_id or "cinematic-studio-3",
            duration_sec=request.duration_sec,
            cost=0.0,
            metadata={"dry_run": True, "prompt": request.prompt},
        )

    async def get_job_status(self, job_id: str) -> GenerationResult:
        if self._dry_run or job_id.startswith("dry-run-"):
            return GenerationResult(
                job_id=job_id, status=JobStatus.COMPLETED,
                provider=self.name, model_id="dry-run", cost=0.0,
            )
        client = await self._get_client()
        resp = await client.get(f"/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        status_map = {"queued": JobStatus.QUEUED, "processing": JobStatus.PROCESSING,
                       "completed": JobStatus.COMPLETED, "failed": JobStatus.FAILED,
                       "cancelled": JobStatus.CANCELLED}
        raw_status = data.get("status", "queued").lower()
        return GenerationResult(
            job_id=job_id,
            status=status_map.get(raw_status, JobStatus.QUEUED),
            provider=self.name,
            model_id=data.get("model", "unknown"),
            output_url=data.get("output_url", data.get("video_url")),
            duration_sec=data.get("duration"),
            cost=data.get("cost"),
            error=data.get("error"),
            metadata=data,
        )

    async def wait_for_job(self, job_id: str, timeout_sec: float = 600) -> GenerationResult:
        if self._dry_run or job_id.startswith("dry-run-"):
            return await self.get_job_status(job_id)
        deadline = time.time() + timeout_sec
        poll_interval = 3.0
        while time.time() < deadline:
            result = await self.get_job_status(job_id)
            if result.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return result
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.2, 15.0)
        raise GenerationError(f"Job {job_id} timed out after {timeout_sec}s", provider=self.name)

    async def cancel_job(self, job_id: str) -> bool:
        if self._dry_run:
            return True
        client = await self._get_client()
        resp = await client.post(f"/jobs/{job_id}/cancel")
        return resp.status_code < 400

    async def download_output(self, job_id: str, dest: Path) -> Path:
        if self._dry_run:
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / f"{job_id}.mp4"
            out.write_bytes(b"")  # empty placeholder
            return out
        result = await self.get_job_status(job_id)
        if not result.output_url:
            raise GenerationError(f"No output URL for job {job_id}", provider=self.name)
        client = await self._get_client()
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / f"{job_id}.mp4"
        async with client.stream("GET", result.output_url) as resp:
            resp.raise_for_status()
            with open(out, "wb") as f:
                async for chunk in resp.aiter_bytes(8192):
                    f.write(chunk)
        return out

    async def upload_reference(self, file_path: Path) -> str:
        if self._dry_run:
            return f"dry-run-ref-{file_path.name}"
        client = await self._get_client()
        with open(file_path, "rb") as f:
            resp = await client.post("/uploads", files={"file": (file_path.name, f)})
        resp.raise_for_status()
        data = resp.json()
        return data.get("id", data.get("url", str(uuid.uuid4())))

    def estimate_cost(self, request: GenerationRequest) -> float | None:
        config_rates = self._config.get("cost_rates", {})
        model = request.model_id or "default"
        rate = config_rates.get(model)
        if rate is not None:
            return float(rate) * request.duration_sec
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
