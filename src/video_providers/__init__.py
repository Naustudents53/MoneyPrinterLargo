"""Video generation provider abstraction layer."""
from .base import (
    VideoGenerationProvider, GenerationRequest, GenerationResult,
    JobStatus, ModelCapabilities, QualityMode,
)
from .errors import VideoProviderError
from .capabilities import CapabilityRegistry


_providers: dict[str, type[VideoGenerationProvider]] = {}


def register_provider(name: str, cls: type[VideoGenerationProvider]) -> None:
    _providers[name] = cls


def get_provider(name: str, **kwargs) -> VideoGenerationProvider:
    if name not in _providers:
        _discover_providers()
    if name not in _providers:
        raise VideoProviderError(f"Unknown video provider: {name}", provider=name)
    return _providers[name](**kwargs)


def list_providers() -> list[str]:
    _discover_providers()
    return list(_providers.keys())


def _discover_providers():
    if "higgsfield" not in _providers:
        from .higgsfield import HiggsfieldProvider
        _providers["higgsfield"] = HiggsfieldProvider
