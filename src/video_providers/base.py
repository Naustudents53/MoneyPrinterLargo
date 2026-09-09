"""Abstract base for video generation providers."""
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from pathlib import Path


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QualityMode(str, Enum):
    BUDGET = "budget"
    BALANCED = "balanced"
    QUALITY = "quality"
    CINEMA = "cinema"


@dataclass
class ModelCapabilities:
    model_id: str
    name: str
    max_duration_sec: float = 10.0
    min_duration_sec: float = 2.0
    supported_aspect_ratios: list[str] = field(default_factory=lambda: ["16:9"])
    supported_resolutions: list[str] = field(default_factory=lambda: ["1080p"])
    supports_audio: bool = False
    supports_references: bool = False
    supports_multi_shot: bool = False
    supports_start_frame: bool = False
    supports_end_frame: bool = False
    supports_video_reference: bool = False
    estimated_cost_per_second: float | None = None
    quality_tier: QualityMode = QualityMode.BALANCED
    tags: list[str] = field(default_factory=list)


@dataclass
class GenerationRequest:
    prompt: str
    negative_prompt: str = ""
    duration_sec: float = 5.0
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    model_id: str | None = None
    quality: QualityMode = QualityMode.QUALITY
    reference_images: list[str] = field(default_factory=list)
    reference_videos: list[str] = field(default_factory=list)
    start_frame: str | None = None
    end_frame: str | None = None
    seed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    job_id: str
    status: JobStatus
    provider: str
    model_id: str
    output_path: str | None = None
    output_url: str | None = None
    duration_sec: float | None = None
    cost: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VideoGenerationProvider(abc.ABC):
    """Abstract base for video generation providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    async def authenticate(self) -> bool: ...

    @abc.abstractmethod
    async def list_models(self) -> list[ModelCapabilities]: ...

    @abc.abstractmethod
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...

    @abc.abstractmethod
    async def get_job_status(self, job_id: str) -> GenerationResult: ...

    @abc.abstractmethod
    async def wait_for_job(self, job_id: str, timeout_sec: float = 600) -> GenerationResult: ...

    @abc.abstractmethod
    async def cancel_job(self, job_id: str) -> bool: ...

    @abc.abstractmethod
    async def download_output(self, job_id: str, dest: Path) -> Path: ...

    async def upload_reference(self, file_path: Path) -> str:
        raise NotImplementedError(f"{self.name} does not support reference uploads")

    def estimate_cost(self, request: GenerationRequest) -> float | None:
        return None
