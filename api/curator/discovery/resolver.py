"""Directory URL resolver.

Given an arbitrary event URL — often a marketing/landing page like
`https://www.snowflake.com/en/summit/` that lists 0–10 anchor logos and links
the actual partner catalog several clicks away — find the canonical page that
contains the full exhibitor/sponsor/partner directory.

The resolver hands its output back to the existing platform-adapter registry,
so a resolved URL that happens to be MapYourShow ends up on the MapYourShow
adapter, etc. RainFocus catalogs currently fall through to `firecrawl_llm`
because `RainFocusAdapter` is gated until its extraction is implemented.

Cached in the local SQLite `enrichment_cache` (provider = "directory_resolver",
key = normalized URL) so reruns don't re-bill Firecrawl.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from curator.config import Settings
from curator.discovery.rainfocus import looks_like_rainfocus
from curator.storage import db as storage_db

PROVIDER_ID = "directory_resolver"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "directory_url": {
            "type": "string",
            "description": (
                "URL of the page that contains the full exhibitor, sponsor, "
                "or partner directory for this event. Empty string if none "
                "exists or cannot be located."
            ),
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "label": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["url"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["directory_url"],
}

PROMPT = (
    "You are looking for the canonical page that lists every exhibitor, "
    "sponsor, or partner for this event. Start at the given URL and follow "
    "navigation links such as 'Sponsors', 'Exhibitors', 'Partners', "
    "'Partner Catalog', 'Expo', 'Marketplace', or 'Directory'. The right "
    "page typically shows many company logos or names together (often "
    "200+). If the event uses a separate registration host (e.g. a "
    "RainFocus reg.* subdomain) and the catalog lives there, return that "
    "URL. Return the single best URL in `directory_url`. List other "
    "plausible URLs in `candidates`. If the input URL already is the full "
    "directory, return it unchanged."
)


@dataclass
class ResolvedURL:
    original_url: str
    resolved_url: str
    was_resolved: bool
    candidates: list[dict[str, str]] = field(default_factory=list)
    notes: str | None = None
    source: str = "firecrawl_agent"  # or "passthrough", "cache"


def _normalize_cache_key(url: str) -> str:
    return url.strip().lower().rstrip("/")


def _is_valid_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _matches_ready_specific_adapter(url: str) -> bool:
    """Skip resolution when the URL already hits a non-fallback adapter.

    Decoupled from `discovery.base.resolve` to avoid eagerly importing the
    Firecrawl adapter (and its API-key requirement) just to check a URL.
    """
    from curator.discovery.mapyourshow import MapYourShowAdapter

    if MapYourShowAdapter().matches(url):
        return True
    # RainFocus is gated off in the registry, but its URLs are still a known
    # platform — no point asking FIRE-1 to "find the directory" when the
    # input already is the catalog.
    if looks_like_rainfocus(url):
        return True
    return False


def resolve_directory_url(
    url: str,
    settings: Settings,
    *,
    conn: Any | None = None,
    force_refresh: bool = False,
) -> ResolvedURL:
    """Find the best URL to ingest from, starting from `url`."""
    if _matches_ready_specific_adapter(url):
        return ResolvedURL(
            original_url=url,
            resolved_url=url,
            was_resolved=False,
            source="passthrough",
        )

    owns_conn = conn is None
    if owns_conn:
        conn = storage_db.connect(settings.db_path)

    try:
        cache_key = _normalize_cache_key(url)
        if not force_refresh:
            cached = storage_db.cache_get(conn, PROVIDER_ID, cache_key)
            if cached is not None:
                resolved = cached.get("resolved_url") or url
                print(
                    f"[resolver] cache hit url={url} -> {resolved}",
                    file=sys.stderr,
                )
                return ResolvedURL(
                    original_url=url,
                    resolved_url=resolved,
                    was_resolved=resolved != url,
                    candidates=cached.get("candidates") or [],
                    notes=cached.get("notes"),
                    source="cache",
                )

        payload = _call_firecrawl_agent(url, settings)
        directory = payload.get("directory_url") or ""
        candidates = payload.get("candidates") or []
        notes = payload.get("notes") or None

        resolved = directory if _is_valid_url(directory) else url
        if resolved == url:
            for cand in candidates:
                if isinstance(cand, dict) and _is_valid_url(cand.get("url")):
                    resolved = cand["url"]
                    break

        # Only cache positive resolutions — a transient FIRE-1 miss shouldn't
        # bake "no directory found" in for next time.
        if resolved != url:
            storage_db.cache_put(
                conn,
                PROVIDER_ID,
                cache_key,
                {
                    "resolved_url": resolved,
                    "candidates": candidates,
                    "notes": notes,
                },
            )
            print(
                f"[resolver] resolved {url} -> {resolved}",
                file=sys.stderr,
            )
        else:
            print(
                f"[resolver] no directory URL found for {url}; ingesting as-is",
                file=sys.stderr,
            )

        return ResolvedURL(
            original_url=url,
            resolved_url=resolved,
            was_resolved=resolved != url,
            candidates=[c for c in candidates if isinstance(c, dict)],
            notes=notes,
            source="firecrawl_agent",
        )
    finally:
        if owns_conn:
            conn.close()


def _call_firecrawl_agent(url: str, settings: Settings) -> dict[str, Any]:
    api_key = settings.firecrawl_api_key or os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        # Without Firecrawl we can't resolve — return empty so the caller
        # falls back to the original URL. This keeps the resolver optional.
        print(
            "[resolver] FIRECRAWL_API_KEY not set; skipping resolution",
            file=sys.stderr,
        )
        return {}

    try:
        from firecrawl import Firecrawl
        from firecrawl.v2.types import JsonFormat
    except ImportError:
        print(
            "[resolver] firecrawl package not installed; skipping resolution",
            file=sys.stderr,
        )
        return {}

    client = Firecrawl(api_key=api_key)
    try:
        result = client.scrape(
            url,
            formats=[JsonFormat(type="json", prompt=PROMPT, schema=SCHEMA)],
            only_main_content=False,
            timeout=180_000,
        )
    except Exception as exc:
        print(f"[resolver] firecrawl scrape failed for {url!r}: {exc}", file=sys.stderr)
        return {}

    return _result_to_dict(result)


def _result_to_dict(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        for key in ("json", "data"):
            v = result.get(key)
            if isinstance(v, dict):
                return v
        return result if "directory_url" in result else {}
    for attr in ("json", "data"):
        value = getattr(result, attr, None)
        if isinstance(value, dict):
            return value
        if value is not None and hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
    if hasattr(result, "model_dump"):
        try:
            dumped = result.model_dump()
            if isinstance(dumped, dict):
                for key in ("json", "data"):
                    v = dumped.get(key)
                    if isinstance(v, dict):
                        return v
        except Exception:
            pass
    return {}
