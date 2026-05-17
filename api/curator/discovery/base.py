from __future__ import annotations

from typing import Protocol, runtime_checkable

from curator.models import EventHints, EventMeta, RawExhibitor


@runtime_checkable
class PlatformAdapter(Protocol):
    platform_id: str

    def matches(self, url: str) -> bool: ...

    def fetch(
        self, url: str, hints: EventHints, *, force_refresh: bool = False
    ) -> tuple[EventMeta, list[RawExhibitor]]: ...


def _build_registry() -> list[PlatformAdapter]:
    # Import lazily to avoid circular imports during module init.
    from curator.discovery.mapyourshow import MapYourShowAdapter
    from curator.discovery.rainfocus import RainFocusAdapter
    from curator.discovery.firecrawl_llm import FirecrawlLLMAdapter

    # Order matters: most-specific first, fallback last.
    return [
        RainFocusAdapter(),
        MapYourShowAdapter(),
        FirecrawlLLMAdapter(),
    ]


_REGISTRY: list[PlatformAdapter] | None = None


def REGISTRY() -> list[PlatformAdapter]:  # noqa: N802 — module-level singleton accessor
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def resolve(url: str, *, force: str | None = None) -> PlatformAdapter:
    registry = REGISTRY()
    if force:
        for adapter in registry:
            if adapter.platform_id == force:
                return adapter
        raise ValueError(f"unknown adapter id: {force}")
    for adapter in registry:
        if adapter.matches(url):
            return adapter
    return registry[-1]  # firecrawl fallback always matches, but defensive
