"""Service layer — pipeline invocation shared between CLI and HTTP API."""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date

from curator.config import Settings
from curator.discovery.base import resolve
from curator.discovery.resolver import resolve_directory_url
from curator.enrichment.agent_enricher import run_prefetch_sync as run_agent_prefetch_sync
from curator.enrichment.overlays import select_overlay
from curator.enrichment.pipeline import build_default_enrichers, run_enrichers
from curator.models import EventHints, EventMeta, NotionRow
from curator.people_enrichment import prefetch_and_store_contacts
from curator.sinks.sqlite_sink import SQLiteSink
from curator.storage import db as storage_db

log = logging.getLogger(__name__)


@dataclass
class IngestOutcome:
    event: EventMeta
    event_id: int
    conference: str | None
    created: int
    updated: int
    skipped: int
    requested_url: str
    resolved_url: str
    was_resolved: bool


def ingest_event(
    *,
    url: str,
    settings: Settings,
    conference: str | None = None,
    event_name: str | None = None,
    event_date: date | None = None,
    venue: str | None = "Moscone Center",
    overlay: str | None = None,
    adapter_override: str | None = None,
    enrichers: list[str] | None = None,
    limit: int | None = None,
    resolve_directory: bool = True,
    force_refresh: bool = False,
) -> IngestOutcome:
    hints = EventHints(
        conference=conference,
        event_name=event_name,
        event_date=event_date,
        venue=venue,
        overlay=overlay,
    )
    if resolve_directory:
        resolution = resolve_directory_url(
            url, settings, force_refresh=force_refresh
        )
        fetch_url = resolution.resolved_url
        if resolution.was_resolved:
            print(
                f"[ingest] resolver: {url} -> {fetch_url}",
                file=sys.stderr,
            )
    else:
        fetch_url = url

    force = adapter_override if adapter_override and adapter_override != "auto" else None
    adapter = resolve(fetch_url, force=force)
    meta, exhibitors = adapter.fetch(fetch_url, hints, force_refresh=force_refresh)
    if limit:
        exhibitors = exhibitors[:limit]

    enricher_ids = enrichers or settings.enricher_order
    prefetched_agent: dict[str, dict] = {}
    if "agent_enricher" in enricher_ids:
        try:
            prefetched_agent = run_agent_prefetch_sync(
                list(exhibitors), settings, force_refresh=force_refresh
            )
        except Exception as exc:
            # SDK auth/transport failures shouldn't 500 the ingest. AgentEnricher
            # no-ops on missing keys, so per-exhibitor enrichment degrades to the
            # other configured enrichers (or returns minimal records).
            log.warning("[agent_enricher] prefetch failed, continuing without it: %s", exc)
    enricher_chain = build_default_enrichers(
        enricher_ids, prefetched_agent=prefetched_agent
    )
    overlay_obj = select_overlay(source_url=url, override=overlay)

    final_conference = conference or meta.name

    rows: list[NotionRow] = []
    for exhibitor in exhibitors:
        profile = run_enrichers(exhibitor, enricher_chain, overlay_obj)
        rows.append(
            NotionRow(
                company=profile,
                conference=final_conference,
                event_date=event_date or meta.start_date,
            )
        )

    sink = SQLiteSink(settings=settings, conference=final_conference)
    result = sink.write(meta, rows)

    # Sink writes rows then returns counts; query the actual event id.
    conn = storage_db.connect(settings.db_path)
    try:
        event_row = conn.execute(
            "SELECT id FROM events WHERE platform = ? AND platform_event_id = ?",
            (meta.platform, meta.platform_event_id),
        ).fetchone()
        event_id = int(event_row["id"]) if event_row else 0
    finally:
        conn.close()

    if event_id:
        people_inputs = [
            (notion_row.company.name_normalized, notion_row.company.display_name)
            for notion_row in rows
        ]
        prefetch_and_store_contacts(event_id, people_inputs, settings)

    return IngestOutcome(
        event=meta,
        event_id=event_id,
        conference=final_conference,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        requested_url=url,
        resolved_url=fetch_url,
        was_resolved=fetch_url != url,
    )
