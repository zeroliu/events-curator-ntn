from __future__ import annotations

import asyncio
import logging
import sqlite3

from curator.config import Settings
from curator.people_enrichment.apollo import apollo_lookup
from curator.people_enrichment.llm import claude_research
from curator.people_enrichment.models import ResearchResult
from curator.storage import db as storage_db
from curator.storage import repo

log = logging.getLogger(__name__)

CACHE_PROVIDER = "people_enricher"
PEOPLE_CONCURRENCY = 5


async def enrich_company_contact(company_name: str, settings: Settings) -> ResearchResult:
    """Apollo first (if configured), Claude Agent SDK + WebSearch otherwise.
    Raises RuntimeError when no usable provider is available."""
    if settings.apollo_api_key:
        result = await asyncio.to_thread(apollo_lookup, company_name, settings.apollo_api_key)
        if result is not None:
            return result
        log.info("[enrich] Apollo returned nothing for %r, falling back to Claude", company_name)

    try:
        return await claude_research(company_name)
    except Exception as exc:  # CLI missing, not signed in, etc.
        raise RuntimeError(f"Claude Agent SDK call failed for {company_name!r}: {exc}") from exc


def _cache_get(conn: sqlite3.Connection, name_norm: str) -> ResearchResult | None:
    payload = storage_db.cache_get(conn, CACHE_PROVIDER, name_norm)
    if payload is None:
        return None
    return ResearchResult.model_validate(payload)


def _cache_put(conn: sqlite3.Connection, name_norm: str, result: ResearchResult) -> None:
    storage_db.cache_put(conn, CACHE_PROVIDER, name_norm, result.model_dump(mode="json"))


async def enrich_companies_parallel(
    companies: list[tuple[str, str]],
    settings: Settings,
    concurrency: int = PEOPLE_CONCURRENCY,
) -> dict[str, ResearchResult]:
    """Run enrich_company_contact for many (name_normalized, display_name) pairs
    concurrently with a semaphore cap. Per-company failures are logged and
    dropped from the result dict."""
    sem = asyncio.Semaphore(concurrency)

    async def one(name_norm: str, display: str) -> tuple[str, ResearchResult] | None:
        async with sem:
            try:
                result = await enrich_company_contact(display, settings)
                return name_norm, result
            except Exception as exc:
                log.warning("[people] enrichment failed for %r: %s", display, exc)
                return None

    outcomes = await asyncio.gather(*(one(n, d) for n, d in companies))
    return dict(item for item in outcomes if item is not None)


def prefetch_and_store_contacts(
    event_id: int,
    companies: list[tuple[str, str]],
    settings: Settings,
) -> None:
    """For each (name_normalized, display_name): skip if a per-event contact row
    already exists; else use the global enrichment_cache; else run live (in
    parallel, capped by PEOPLE_CONCURRENCY). Fresh results are written to both
    the global cache and the per-event row. Best-effort — never raises."""
    if not companies:
        return

    conn = storage_db.connect(settings.db_path)
    try:
        live_needed: list[tuple[str, str]] = []
        for name_norm, display in companies:
            if repo.get_contact(conn, event_id, name_norm) is not None:
                continue
            cached = _cache_get(conn, name_norm)
            if cached is not None:
                repo.upsert_contact(conn, event_id, name_norm, cached)
                log.info("[people] global cache hit %s", name_norm)
                continue
            live_needed.append((name_norm, display))
    finally:
        conn.close()

    if not live_needed:
        return

    log.info("[people] live enrichment for %d companies", len(live_needed))
    try:
        results = asyncio.run(enrich_companies_parallel(live_needed, settings))
    except Exception as exc:
        log.warning("[people] parallel enrichment crashed: %s", exc)
        return

    conn = storage_db.connect(settings.db_path)
    try:
        for name_norm, result in results.items():
            _cache_put(conn, name_norm, result)
            repo.upsert_contact(conn, event_id, name_norm, result)
    finally:
        conn.close()
