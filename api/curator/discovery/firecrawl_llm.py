"""Firecrawl-backed discovery adapter.

Fallback adapter for any URL no specific platform adapter handles. Uses
Firecrawl's `/extract` with the FIRE-1 agent so it can navigate from a
sponsors/exhibitors index page into each exhibitor's detail page when needed.

Results are cached in the local SQLite `enrichment_cache` table
(provider = "firecrawl_discovery", key = normalized URL) so reruns don't
re-bill Firecrawl. Pass `force_refresh=True` to bypass the cache.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any
from urllib.parse import urlparse

from curator.config import Settings
from curator.models import EventHints, EventMeta, RawExhibitor
from curator.storage import db as storage_db


_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_CHROME_EXACT = {
    "sponsors",
    "exhibitors",
    "partners",
    "load more",
    "show more",
    "back to top",
}
_PAGE_CHROME_PREFIXES = ("view all", "see all", "show all")

PROVIDER_ID = "firecrawl_discovery"

# Tuned against RainFocus catalogs that render ~30 cards per viewport. 8 steps
# covers ~240 exhibitors which spans the long tail of shows we ingest; if a
# real event exceeds that, the count will plateau and the next bump can land
# behind data instead of speculation.
_SCROLL_STEPS = 8
_SCROLL_WAIT_MS = 1500

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "event_name": {"type": "string"},
        "exhibitors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "booth": {"type": "string"},
                    "website": {"type": "string"},
                    "official_description": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["exhibitors"],
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip()


def _normalize_cache_key(url: str) -> str:
    return url.strip().lower().rstrip("/")


def _looks_like_page_chrome(name: str) -> bool:
    if len(name) < 2:
        return True
    lowered = name.lower()
    if lowered in _PAGE_CHROME_EXACT:
        return True
    return any(lowered.startswith(prefix) for prefix in _PAGE_CHROME_PREFIXES)


def _derive_event_name_from_url(url: str) -> str:
    host = urlparse(url).hostname or url
    # Strip leading www. for cleanliness.
    return host[4:] if host.startswith("www.") else host


def _derive_platform_event_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "unknown").lower()
    path = parsed.path.strip("/").replace("/", "-") or "root"
    return f"{host}:{path}"


class FirecrawlLLMAdapter:
    """LLM-driven fallback that scrapes a sponsors/exhibitors page via Firecrawl.

    Always matches so the registry can fall back to it.
    """

    platform_id = "firecrawl_llm"

    def __init__(self, settings: Settings | None = None) -> None:
        # Defer Settings.load() and Firecrawl import until fetch() — the
        # registry instantiates every adapter eagerly, and adapters that are
        # never invoked shouldn't require FIRECRAWL_API_KEY.
        self._settings = settings
        self._client: Any | None = None
        self._conn = None

    def matches(self, url: str) -> bool:
        return True

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        settings = self._settings or Settings.load()
        self._settings = settings
        api_key = settings.firecrawl_api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "firecrawl_llm adapter requires FIRECRAWL_API_KEY. "
                "Set it in the environment, or pick a specific adapter "
                "with --adapter mapyourshow."
            )
        try:
            from firecrawl import Firecrawl
        except ImportError as exc:
            raise RuntimeError(
                "firecrawl package not installed. "
                "Run `pip install events-curator[firecrawl]` (or `pip install firecrawl-py`)."
            ) from exc
        self._client = Firecrawl(api_key=api_key)
        return self._client

    def _ensure_conn(self):
        if self._conn is None:
            settings = self._settings or Settings.load()
            self._settings = settings
            self._conn = storage_db.connect(settings.db_path)
        return self._conn

    def fetch(
        self, url: str, hints: EventHints, *, force_refresh: bool = False
    ) -> tuple[EventMeta, list[RawExhibitor]]:
        conn = self._ensure_conn()
        cache_key = _normalize_cache_key(url)

        payload: dict[str, Any] | None = None
        if not force_refresh:
            payload = storage_db.cache_get(conn, PROVIDER_ID, cache_key)
            if payload is not None:
                print(
                    f"[firecrawl_llm] cache hit url={url}",
                    file=sys.stderr,
                )

        if payload is None:
            payload = self._call_firecrawl(url)
            # Don't poison the cache with an empty extraction — a transient
            # FIRE-1 failure shouldn't bake in zero exhibitors for next time.
            if payload.get("exhibitors"):
                storage_db.cache_put(conn, PROVIDER_ID, cache_key, payload)
            else:
                print(
                    f"[firecrawl_llm] empty extraction (not cached) for {url}",
                    file=sys.stderr,
                )

        exhibitors = _payload_to_exhibitors(payload, source_url=url)
        event_name = (
            hints.event_name
            or _clean(payload.get("event_name"))
            or _derive_event_name_from_url(url)
        )
        meta = EventMeta(
            name=event_name,
            platform=self.platform_id,
            platform_event_id=_derive_platform_event_id(url),
            source_url=url,
            venue=hints.venue,
            start_date=hints.event_date,
            end_date=hints.event_date,
        )
        return meta, exhibitors

    def _call_firecrawl(self, url: str) -> dict[str, Any]:
        client = self._ensure_client()
        prompt = (
            "Extract every exhibitor, sponsor, or partner listed on this "
            "page. Include all sponsor tiers (Platinum / Gold / Silver, "
            "Diamond / Sapphire, etc.). For each, capture company name, "
            "booth number or sponsor tier if shown, and the company website "
            "if linked. Do not include navigation links, filter chips, "
            "or page chrome."
        )
        # /extract is in maintenance mode per the SDK; /scrape with JsonFormat
        # is the supported replacement and tested far more reliable on flat
        # directory pages (e.g. abainternational.org). only_main_content=False
        # keeps tables/footers/sidebars that often hold exhibitor listings.
        from firecrawl.v2.types import JsonFormat, ScrollAction, WaitAction

        # Many event catalogs (RainFocus, Cvent, etc.) lazy-render the company
        # grid client-side and only mount more rows as the user scrolls. Without
        # these actions, Firecrawl sees the empty shell — e.g. Snowflake Summit
        # 26's catalog returned 1 row vs 200 with scrolls. Wait once for the
        # initial render, then scroll a handful of times to flush the rest.
        actions = [WaitAction(milliseconds=5000)]
        for _ in range(_SCROLL_STEPS):
            actions.append(ScrollAction(direction="down"))
            actions.append(WaitAction(milliseconds=_SCROLL_WAIT_MS))

        try:
            result = client.scrape(
                url,
                formats=[JsonFormat(type="json", prompt=prompt, schema=SCHEMA)],
                only_main_content=False,
                actions=actions,
                timeout=600_000,  # scrape timeouts are milliseconds
            )
        except Exception as exc:
            raise RuntimeError(
                f"Firecrawl scrape failed for {url!r}: {exc}"
            ) from exc

        data = _result_to_dict(result)
        if not data:
            raise RuntimeError(
                f"Firecrawl returned no JSON payload for {url!r}."
            )
        return {
            "event_name": data.get("event_name"),
            "exhibitors": data.get("exhibitors") or [],
        }


def _payload_to_exhibitors(
    payload: dict[str, Any], *, source_url: str
) -> list[RawExhibitor]:
    items = payload.get("exhibitors") or []
    if not isinstance(items, list):
        return []

    exhibitors: list[RawExhibitor] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name or _looks_like_page_chrome(name):
            continue

        website = _clean(item.get("website")) or None
        booth = _clean(item.get("booth")) or None
        desc = _clean(item.get("official_description")) or None
        item_source = _clean(item.get("source_url")) or source_url

        confidence = "high" if website else "medium"

        exhibitors.append(
            RawExhibitor(
                name=name,
                booth=booth,
                official_description=desc,
                website=website,
                source_url=item_source,
                raw_payload=item if isinstance(item, dict) else {},
                extraction_confidence=confidence,
            )
        )
    return exhibitors


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Pull the structured payload out of a Firecrawl Document or ExtractResponse.

    scrape() with JsonFormat exposes it as `result.json` (a dict). extract()
    exposes it as `result.data`. Older paths return raw dicts.
    """
    if result is None:
        return {}
    if isinstance(result, dict):
        for key in ("json", "data"):
            v = result.get(key)
            if isinstance(v, dict):
                return v
        return result if "exhibitors" in result else {}
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
