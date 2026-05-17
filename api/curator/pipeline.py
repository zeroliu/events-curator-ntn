from __future__ import annotations

import argparse
import sys
from pathlib import Path

from curator.config import Settings
from curator.discovery.base import resolve
from curator.discovery.resolver import resolve_directory_url
from curator.enrichment.overlays import select_overlay
from curator.enrichment.pipeline import build_default_enrichers, run_enrichers
from curator.models import EventHints, NotionRow
from curator.sinks.base import Sink, SinkResult


def _build_sink(args: argparse.Namespace, settings: Settings, conference: str | None) -> Sink:
    if args.sink == "csv":
        if not args.output:
            raise SystemExit("--sink=csv requires --output PATH")
        from curator.sinks.csv_sink import CSVSink

        legacy = bool(args.overlay or "apa26" in (args.url or ""))
        return CSVSink(args.output, legacy=legacy)
    if args.sink == "stdout":
        from curator.sinks.stdout_sink import StdoutSink

        return StdoutSink()
    if args.sink == "sqlite":
        from curator.sinks.sqlite_sink import SQLiteSink

        return SQLiteSink(settings=settings, conference=conference)
    raise SystemExit(f"unknown sink: {args.sink}")


def run_ingest(args: argparse.Namespace, settings: Settings) -> int:
    hints = EventHints(
        conference=args.conference,
        event_name=args.event_name,
        event_date=args.event_date,
        venue=args.venue,
        overlay=args.overlay,
    )
    fetch_url = args.url
    if not getattr(args, "no_resolve", False):
        resolution = resolve_directory_url(
            args.url,
            settings,
            force_refresh=getattr(args, "force_refresh", False),
        )
        fetch_url = resolution.resolved_url
        if resolution.was_resolved:
            print(
                f"[ingest] resolver: {args.url} -> {fetch_url}",
                file=sys.stderr,
            )

    force = None if args.adapter == "auto" else args.adapter
    adapter = resolve(fetch_url, force=force)
    print(f"[ingest] adapter={adapter.platform_id} url={fetch_url}", file=sys.stderr)
    meta, exhibitors = adapter.fetch(
        fetch_url, hints, force_refresh=getattr(args, "force_refresh", False)
    )

    if args.limit:
        exhibitors = exhibitors[: args.limit]

    enrichers = build_default_enrichers(settings.enricher_order)
    overlay = select_overlay(source_url=args.url, override=args.overlay)
    overlay_id = getattr(overlay, "provider_id", None) if overlay else None
    # Conference defaults to the event name; --conference is an override.
    conference = args.conference or meta.name
    print(
        f"[ingest] event={meta.name!r} conference={conference!r} "
        f"exhibitors={len(exhibitors)} "
        f"enrichers={[e.provider_id for e in enrichers]} overlay={overlay_id}",
        file=sys.stderr,
    )

    rows: list[NotionRow] = []
    for exhibitor in exhibitors:
        profile = run_enrichers(exhibitor, enrichers, overlay)
        rows.append(
            NotionRow(
                company=profile,
                conference=conference,
                event_date=args.event_date or meta.start_date,
            )
        )

    sink = _build_sink(args, settings, conference)
    result: SinkResult = sink.write(meta, rows)
    print(
        f"[ingest] sink={sink.sink_id} created={result.created} "
        f"updated={result.updated} skipped={result.skipped}",
        file=sys.stderr,
    )
    return 0
