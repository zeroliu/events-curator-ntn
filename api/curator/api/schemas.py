from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EventSummary(BaseModel):
    id: int
    name: str
    platform: str
    platform_event_id: str
    source_url: str
    conference: str | None = None
    venue: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    last_ingested_at: str
    company_count: int


class Company(BaseModel):
    name_normalized: str
    display_name: str
    booth: str | None = None
    official_description: str | None = None
    website: str | None = None
    industry: str | None = None
    size_bucket: str | None = None
    wealth_tier: str | None = None
    priority: str | None = None
    score: int | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    notes_appendix: str | None = None
    extraction_confidence: str | None = None
    extras: dict[str, Any] | None = None
    enrichment_sources: dict[str, Any] | None = None
    raw_payload: dict[str, Any] | None = None
    source_url: str | None = None
    updated_at: str


class CompanyPage(BaseModel):
    event_id: int
    total: int
    limit: int
    offset: int
    items: list[Company]


class IngestRequest(BaseModel):
    url: str
    conference: str | None = None
    event_name: str | None = None
    event_date: str | None = Field(default=None, description="ISO date (YYYY-MM-DD)")
    venue: str | None = None
    overlay: str | None = None
    adapter: str | None = Field(default=None, description="auto|mapyourshow|rainfocus|firecrawl_llm")
    enrichers: list[str] | None = None
    limit: int | None = None
    resolve_directory: bool = Field(
        default=True,
        description=(
            "If true (default), run the directory resolver to follow a "
            "marketing/landing page to its canonical exhibitor list before "
            "ingesting."
        ),
    )
    force_refresh: bool = Field(
        default=False,
        description="Bypass resolver + adapter caches.",
    )


class IngestResponse(BaseModel):
    event_id: int
    event: EventSummary
    created: int
    updated: int
    skipped: int
    requested_url: str
    resolved_url: str
    was_resolved: bool


class ContactEnrichRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="If true, re-run providers even when a contact is already cached.",
    )


class Contact(BaseModel):
    event_id: int
    name_normalized: str
    person_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    sources: list[str] = []
    confidence: Literal["high", "medium", "low"]
    reasoning: str | None = None
    provider: Literal["apollo", "anthropic"] | None = None
    enriched_at: str
