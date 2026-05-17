from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False so connections cached on module-level singletons
    # (e.g. FirecrawlLLMAdapter._conn) survive across FastAPI threadpool requests.
    # Safe here because FastAPI serializes sync handlers via anyio.to_thread.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cache_get(conn: sqlite3.Connection, provider: str, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM enrichment_cache WHERE provider = ? AND cache_key = ?",
        (provider, key),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def cache_put(
    conn: sqlite3.Connection, provider: str, key: str, payload: dict[str, Any]
) -> None:
    conn.execute(
        """
        INSERT INTO enrichment_cache(provider, cache_key, payload_json, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(provider, cache_key) DO UPDATE SET
            payload_json = excluded.payload_json,
            fetched_at = excluded.fetched_at
        """,
        (provider, key, json.dumps(payload, ensure_ascii=False), _now_iso()),
    )
    conn.commit()


def get_notion_page_id(conn: sqlite3.Connection, name_normalized: str) -> str | None:
    row = conn.execute(
        "SELECT page_id FROM notion_id_by_company WHERE name_normalized = ?",
        (name_normalized,),
    ).fetchone()
    return row["page_id"] if row else None


def put_notion_page_id(
    conn: sqlite3.Connection, name_normalized: str, page_id: str
) -> None:
    conn.execute(
        """
        INSERT INTO notion_id_by_company(name_normalized, page_id, last_synced_at)
        VALUES (?, ?, ?)
        ON CONFLICT(name_normalized) DO UPDATE SET
            page_id = excluded.page_id,
            last_synced_at = excluded.last_synced_at
        """,
        (name_normalized, page_id, _now_iso()),
    )
    conn.commit()


def log_ingest(
    conn: sqlite3.Connection,
    *,
    source_url: str,
    platform: str,
    conference: str | None,
    exhibitor_count: int,
    created_count: int,
    updated_count: int,
    started_at: str,
    finished_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ingest_log(
            source_url, platform, conference, exhibitor_count,
            created_count, updated_count, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_url,
            platform,
            conference,
            exhibitor_count,
            created_count,
            updated_count,
            started_at,
            finished_at,
        ),
    )
    conn.commit()
