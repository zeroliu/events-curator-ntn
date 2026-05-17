"""SQLite sink — persists ingest output to the DB the HTTP API reads from."""
from __future__ import annotations

from curator.config import Settings
from curator.models import EventMeta, NotionRow
from curator.sinks.base import SinkResult
from curator.storage import db as storage_db
from curator.storage import repo


class SQLiteSink:
    sink_id = "sqlite"

    def __init__(self, *, settings: Settings, conference: str | None) -> None:
        self.settings = settings
        self.conference = conference

    def write(self, event: EventMeta, rows: list[NotionRow]) -> SinkResult:
        conn = storage_db.connect(self.settings.db_path)
        try:
            existing_ids: set[tuple[int, str]] = set()
            event_row = conn.execute(
                "SELECT id FROM events WHERE platform = ? AND platform_event_id = ?",
                (event.platform, event.platform_event_id),
            ).fetchone()
            if event_row is not None:
                existing_ids = {
                    (event_row["id"], r["name_normalized"])
                    for r in conn.execute(
                        "SELECT name_normalized FROM event_companies WHERE event_id = ?",
                        (event_row["id"],),
                    ).fetchall()
                }
            event_id, total = repo.write_event_with_companies(
                conn, event, self.conference, rows
            )
            created = 0
            updated = 0
            for row in rows:
                key = (event_id, row.company.name_normalized)
                if key in existing_ids:
                    updated += 1
                else:
                    created += 1
            return SinkResult(created=created, updated=updated)
        finally:
            conn.close()
