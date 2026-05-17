from __future__ import annotations

from curator.enrichment.overlays.apa26 import APA26Overlay


def select_overlay(*, source_url: str, override: str | None) -> object | None:
    if override:
        if override.lower() in {"apa26", "apa-26", "apa"}:
            return APA26Overlay()
        return None
    if "apa26.mapyourshow.com" in source_url:
        return APA26Overlay()
    return None
