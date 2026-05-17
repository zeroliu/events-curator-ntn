"""Read/write helpers for events + event_companies."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from curator.models import (
    CompanyProfile,
    EventMeta,
    NotionRow,
    RawExhibitor,
)
from curator.people_enrichment.models import ResearchResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_event(
    conn: sqlite3.Connection, meta: EventMeta, *, conference: str | None
) -> int:
    cur = conn.execute(
        """
        INSERT INTO events (
            platform, platform_event_id, name, source_url, conference,
            venue, start_date, end_date, last_ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, platform_event_id) DO UPDATE SET
            name = excluded.name,
            source_url = excluded.source_url,
            conference = excluded.conference,
            venue = excluded.venue,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            last_ingested_at = excluded.last_ingested_at
        """,
        (
            meta.platform,
            meta.platform_event_id,
            meta.name,
            meta.source_url,
            conference,
            meta.venue,
            meta.start_date.isoformat() if meta.start_date else None,
            meta.end_date.isoformat() if meta.end_date else None,
            _now_iso(),
        ),
    )
    if cur.lastrowid:
        event_id = cur.lastrowid
    else:
        row = conn.execute(
            "SELECT id FROM events WHERE platform = ? AND platform_event_id = ?",
            (meta.platform, meta.platform_event_id),
        ).fetchone()
        event_id = row["id"]
    conn.commit()
    return int(event_id)


def upsert_event_company(
    conn: sqlite3.Connection, event_id: int, row: NotionRow
) -> None:
    company = row.company
    raw = company.raw_exhibitor or RawExhibitor(name=company.display_name)
    conn.execute(
        """
        INSERT INTO event_companies (
            event_id, name_normalized, display_name, booth, official_description,
            website, industry, size_bucket, wealth_tier, priority, score,
            hq_city, hq_country, notes_appendix, extraction_confidence,
            extras_json, enrichment_sources_json, raw_payload_json,
            source_url, gmv_usd, gmv_confidence, gmv_note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, name_normalized) DO UPDATE SET
            display_name = excluded.display_name,
            booth = excluded.booth,
            official_description = excluded.official_description,
            website = excluded.website,
            industry = excluded.industry,
            size_bucket = excluded.size_bucket,
            wealth_tier = excluded.wealth_tier,
            priority = excluded.priority,
            score = excluded.score,
            hq_city = excluded.hq_city,
            hq_country = excluded.hq_country,
            notes_appendix = excluded.notes_appendix,
            extraction_confidence = excluded.extraction_confidence,
            extras_json = excluded.extras_json,
            enrichment_sources_json = excluded.enrichment_sources_json,
            raw_payload_json = excluded.raw_payload_json,
            source_url = excluded.source_url,
            gmv_usd = excluded.gmv_usd,
            gmv_confidence = excluded.gmv_confidence,
            gmv_note = excluded.gmv_note,
            updated_at = excluded.updated_at
        """,
        (
            event_id,
            company.name_normalized,
            company.display_name,
            raw.booth,
            raw.official_description,
            company.website or raw.website,
            company.industry,
            company.size_bucket,
            company.wealth_tier,
            company.priority,
            company.score,
            company.hq_city,
            company.hq_country,
            company.notes_appendix,
            raw.extraction_confidence,
            json.dumps(company.extras, ensure_ascii=False) if company.extras else None,
            json.dumps(company.enrichment_sources, ensure_ascii=False)
            if company.enrichment_sources
            else None,
            json.dumps(raw.raw_payload, ensure_ascii=False) if raw.raw_payload else None,
            raw.source_url,
            company.gmv_usd,
            company.gmv_confidence,
            company.gmv_note,
            _now_iso(),
        ),
    )
    conn.commit()


def list_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.*, (
            SELECT COUNT(*) FROM event_companies ec WHERE ec.event_id = e.id
        ) AS company_count
        FROM events e
        ORDER BY e.last_ingested_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_event(conn: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT e.*, (
            SELECT COUNT(*) FROM event_companies ec WHERE ec.event_id = e.id
        ) AS company_count
        FROM events e
        WHERE e.id = ?
        """,
        (event_id,),
    ).fetchone()
    return dict(row) if row else None


def list_companies(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    industry: str | None = None,
    priority: str | None = None,
    wealth_tier: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = ["event_id = ?"]
    params: list[Any] = [event_id]
    if industry:
        where.append("industry = ?")
        params.append(industry)
    if priority:
        where.append("priority = ?")
        params.append(priority)
    if wealth_tier:
        where.append("wealth_tier = ?")
        params.append(wealth_tier)
    where_clause = " AND ".join(where)

    total = int(
        conn.execute(
            f"SELECT COUNT(*) AS n FROM event_companies WHERE {where_clause}",
            params,
        ).fetchone()["n"]
    )
    rows = conn.execute(
        f"""
        SELECT * FROM event_companies
        WHERE {where_clause}
        ORDER BY score DESC, display_name ASC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("extras_json", "enrichment_sources_json", "raw_payload_json"):
            value = d.pop(k, None)
            d[k.removesuffix("_json")] = json.loads(value) if value else None
        out.append(d)
    return out, total


def get_company(
    conn: sqlite3.Connection, event_id: int, name_normalized: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM event_companies WHERE event_id = ? AND name_normalized = ?",
        (event_id, name_normalized),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    for k in ("extras_json", "enrichment_sources_json", "raw_payload_json"):
        value = d.pop(k, None)
        d[k.removesuffix("_json")] = json.loads(value) if value else None
    return d


def get_contact(
    conn: sqlite3.Connection, event_id: int, name_normalized: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM event_company_contacts WHERE event_id = ? AND name_normalized = ?",
        (event_id, name_normalized),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    sources_raw = d.pop("sources_json", None)
    d["sources"] = json.loads(sources_raw) if sources_raw else []
    return d


def upsert_contact(
    conn: sqlite3.Connection,
    event_id: int,
    name_normalized: str,
    result: ResearchResult,
) -> None:
    conn.execute(
        """
        INSERT INTO event_company_contacts (
            event_id, name_normalized, person_name, title, email, phone,
            sources_json, confidence, reasoning, provider, enriched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, name_normalized) DO UPDATE SET
            person_name = excluded.person_name,
            title = excluded.title,
            email = excluded.email,
            phone = excluded.phone,
            sources_json = excluded.sources_json,
            confidence = excluded.confidence,
            reasoning = excluded.reasoning,
            provider = excluded.provider,
            enriched_at = excluded.enriched_at
        """,
        (
            event_id,
            name_normalized,
            result.person_name,
            result.title,
            result.email,
            result.phone,
            json.dumps(result.sources, ensure_ascii=False) if result.sources else None,
            result.confidence,
            result.reasoning,
            result.provider,
            _now_iso(),
        ),
    )
    conn.commit()


def write_event_with_companies(
    conn: sqlite3.Connection,
    meta: EventMeta,
    conference: str | None,
    rows: Iterable[NotionRow],
) -> tuple[int, int]:
    event_id = upsert_event(conn, meta, conference=conference)
    count = 0
    for row in rows:
        upsert_event_company(conn, event_id, row)
        count += 1
    return event_id, count
