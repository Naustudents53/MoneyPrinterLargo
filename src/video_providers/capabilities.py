"""Runtime capability discovery for video providers."""
from __future__ import annotations
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from .base import ModelCapabilities


CACHE_TTL_SEC = 3600  # 1 hour


@dataclass
class ProviderCapabilities:
    provider: str
    models: list[ModelCapabilities]
    fetched_at: float = 0.0

    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > CACHE_TTL_SEC


class CapabilityRegistry:
    """Caches and serves discovered provider capabilities."""

    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ProviderCapabilities] = {}

    def _cache_path(self, provider: str) -> Path:
        return self._cache_dir / f"{provider}_capabilities.json"

    def get(self, provider: str) -> ProviderCapabilities | None:
        if provider in self._cache and not self._cache[provider].is_stale():
            return self._cache[provider]
        path = self._cache_path(provider)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                caps = ProviderCapabilities(
                    provider=data["provider"],
                    models=[ModelCapabilities(**m) for m in data["models"]],
                    fetched_at=data.get("fetched_at", 0),
                )
                if not caps.is_stale():
                    self._cache[provider] = caps
                    return caps
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return None

    def store(self, caps: ProviderCapabilities) -> None:
        caps.fetched_at = time.time()
        self._cache[caps.provider] = caps
        data = {
            "provider": caps.provider,
            "models": [asdict(m) for m in caps.models],
            "fetched_at": caps.fetched_at,
        }
        self._cache_path(caps.provider).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def get_model(self, provider: str, model_id: str) -> ModelCapabilities | None:
        caps = self.get(provider)
        if not caps:
            return None
        for m in caps.models:
            if m.model_id == model_id:
                return m
        return None
