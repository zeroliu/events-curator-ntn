from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from curator.config import NOTION_CONFERENCE_OPTIONS, Settings


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="curator")
    sub = p.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest an event's exhibitor list.")
    ingest.add_argument("url", help="Event URL (any supported platform; LLM fallback otherwise).")
    ingest.add_argument(
        "--conference",
        help=(
            "Override the conference label that gets attached to every company. "
            "Defaults to the event name discovered from the source (e.g. 'APA 26'). "
            f"Notion's existing select options: {sorted(NOTION_CONFERENCE_OPTIONS)}"
        ),
    )
    ingest.add_argument("--event-name", help="Override event name if scrape fails.")
    ingest.add_argument("--event-date", type=_parse_date, help="ISO event date (YYYY-MM-DD).")
    ingest.add_argument("--venue", default="Moscone Center")
    ingest.add_argument(
        "--adapter",
        choices=["auto", "mapyourshow", "rainfocus", "firecrawl_llm"],
        default="auto",
    )
    ingest.add_argument("--overlay", help="Force a specific overlay (e.g. apa26).")
    ingest.add_argument(
        "--sink",
        choices=["sqlite", "csv", "stdout"],
        default="sqlite",
        help="sqlite (default) writes to the local DB the API serves from.",
    )
    ingest.add_argument("--output", type=Path, help="Output path when --sink=csv.")
    ingest.add_argument(
        "--enrichers",
        help=(
            "Override CURATOR_ENRICHERS, comma-separated. Choices: "
            "agent_enricher (default; requires Claude Code CLI), heuristic, "
            "website_llm, apollo."
        ),
    )
    ingest.add_argument("--limit", type=int, help="Process at most N exhibitors (testing).")
    ingest.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass discovery + agent_enricher caches; refreshed results are still written through.",
    )
    ingest.add_argument(
        "--no-resolve",
        action="store_true",
        help=(
            "Skip the directory resolver — ingest the URL as given. "
            "Default is to follow marketing/landing pages to the canonical "
            "exhibitor/sponsor/partner directory."
        ),
    )

    serve = sub.add_parser("serve", help="Run the HTTP API server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return p


def cmd_ingest(args: argparse.Namespace) -> int:
    # Late imports keep `curator --help` snappy and the bootstrap testable.
    from curator.pipeline import run_ingest

    settings = Settings.load()
    if args.enrichers:
        settings.enricher_order = [s.strip() for s in args.enrichers.split(",") if s.strip()]

    if args.conference and args.conference not in NOTION_CONFERENCE_OPTIONS:
        print(
            f"note: --conference {args.conference!r} is not in Notion's existing "
            "Conference / Trigger options. Add it to the database before running the worker.",
            file=sys.stderr,
        )

    return run_ingest(args, settings)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "curator.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "serve":
        return cmd_serve(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
