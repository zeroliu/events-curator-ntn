from __future__ import annotations

from datetime import date

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query

load_dotenv()

from curator.api.schemas import (
    Company,
    CompanyPage,
    Contact,
    ContactEnrichRequest,
    EventSummary,
    IngestRequest,
    IngestResponse,
)
from curator.api.service import ingest_event
from curator.config import Settings
from curator.people_enrichment import enrich_company_contact
from curator.storage import db as storage_db
from curator.storage import repo


def get_settings() -> Settings:
    return Settings.load()


app = FastAPI(
    title="Moscone Events Curator API",
    version="0.1.0",
    description=(
        "Read-only API the Notion ntn worker pulls from. Ingestion endpoint runs "
        "the discovery + enrichment pipeline against an event URL and stores results "
        "in SQLite; GET endpoints expose those records as snake_case JSON."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/events", response_model=list[EventSummary])
def list_events(settings: Settings = Depends(get_settings)) -> list[EventSummary]:
    conn = storage_db.connect(settings.db_path)
    try:
        return [EventSummary(**row) for row in repo.list_events(conn)]
    finally:
        conn.close()


@app.get("/events/{event_id}", response_model=EventSummary)
def get_event(
    event_id: int, settings: Settings = Depends(get_settings)
) -> EventSummary:
    conn = storage_db.connect(settings.db_path)
    try:
        row = repo.get_event(conn, event_id)
        if row is None:
            raise HTTPException(status_code=404, detail="event not found")
        return EventSummary(**row)
    finally:
        conn.close()


@app.get("/events/{event_id}/companies", response_model=CompanyPage)
def list_event_companies(
    event_id: int,
    industry: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    wealth_tier: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> CompanyPage:
    conn = storage_db.connect(settings.db_path)
    try:
        if repo.get_event(conn, event_id) is None:
            raise HTTPException(status_code=404, detail="event not found")
        rows, total = repo.list_companies(
            conn,
            event_id,
            industry=industry,
            priority=priority,
            wealth_tier=wealth_tier,
            limit=limit,
            offset=offset,
        )
        return CompanyPage(
            event_id=event_id,
            total=total,
            limit=limit,
            offset=offset,
            items=[Company(**r) for r in rows],
        )
    finally:
        conn.close()


def _contact_from_row(row: dict) -> Contact:
    return Contact(
        event_id=row["event_id"],
        name_normalized=row["name_normalized"],
        person_name=row.get("person_name"),
        title=row.get("title"),
        email=row.get("email"),
        phone=row.get("phone"),
        sources=row.get("sources") or [],
        confidence=row["confidence"],
        reasoning=row.get("reasoning"),
        provider=row.get("provider"),
        enriched_at=row["enriched_at"],
    )


@app.get(
    "/events/{event_id}/companies/{name_normalized}/contact",
    response_model=Contact,
)
def get_company_contact(
    event_id: int,
    name_normalized: str,
    settings: Settings = Depends(get_settings),
) -> Contact:
    conn = storage_db.connect(settings.db_path)
    try:
        row = repo.get_contact(conn, event_id, name_normalized)
        if row is None:
            raise HTTPException(status_code=404, detail="contact not enriched yet")
        return _contact_from_row(row)
    finally:
        conn.close()


@app.post(
    "/events/{event_id}/companies/{name_normalized}/contacts:enrich",
    response_model=Contact,
)
async def enrich_company_contact_route(
    event_id: int,
    name_normalized: str,
    body: ContactEnrichRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> Contact:
    force = bool(body and body.force)

    conn = storage_db.connect(settings.db_path)
    try:
        if repo.get_event(conn, event_id) is None:
            raise HTTPException(status_code=404, detail="event not found")
        company = repo.get_company(conn, event_id, name_normalized)
        if company is None:
            raise HTTPException(status_code=404, detail="company not found")

        if not force:
            cached = repo.get_contact(conn, event_id, name_normalized)
            if cached is not None:
                return _contact_from_row(cached)

        display_name = company.get("display_name") or name_normalized
    finally:
        conn.close()

    try:
        result = await enrich_company_contact(display_name, settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    conn = storage_db.connect(settings.db_path)
    try:
        repo.upsert_contact(conn, event_id, name_normalized, result)
        row = repo.get_contact(conn, event_id, name_normalized)
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=500, detail="contact vanished after upsert")
    return _contact_from_row(row)


@app.post("/events/ingest", response_model=IngestResponse)
def ingest(
    request: IngestRequest, settings: Settings = Depends(get_settings)
) -> IngestResponse:
    event_date: date | None = None
    if request.event_date:
        try:
            event_date = date.fromisoformat(request.event_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"bad event_date: {exc}")

    if request.enrichers is not None:
        settings.enricher_order = list(request.enrichers)

    try:
        outcome = ingest_event(
            url=request.url,
            settings=settings,
            conference=request.conference,
            event_name=request.event_name,
            event_date=event_date,
            venue=request.venue or "Moscone Center",
            overlay=request.overlay,
            adapter_override=request.adapter,
            enrichers=request.enrichers,
            limit=request.limit,
            resolve_directory=request.resolve_directory,
            force_refresh=request.force_refresh,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    conn = storage_db.connect(settings.db_path)
    try:
        event_row = repo.get_event(conn, outcome.event_id)
    finally:
        conn.close()
    if event_row is None:
        raise HTTPException(status_code=500, detail="event vanished after ingest")

    return IngestResponse(
        event_id=outcome.event_id,
        event=EventSummary(**event_row),
        created=outcome.created,
        updated=outcome.updated,
        skipped=outcome.skipped,
        requested_url=outcome.requested_url,
        resolved_url=outcome.resolved_url,
        was_resolved=outcome.was_resolved,
    )
