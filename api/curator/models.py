from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


NotionIndustry = Literal[
    "Tech / Software",
    "Healthcare / Pharma",
    "Finance / VC",
    "Legal",
    "Consulting",
    "Education / Research",
    "Hospitality / Events",
    "Government / Non-profit",
    "Gaming / Entertainment",
    "Real Estate",
    "Other",
]

NotionWealthTier = Literal[
    "💎 Mega Cap",
    "🏢 Large Enterprise",
    "📈 Mid-Market",
    "🚀 Funded Startup",
    "🎓 Education / Research",
    "🏛️ Government / Non-profit",
    "🤝 Hospitality Partner",
    "❓ SMB / Personal",
]

NotionPriority = Literal["High", "Mid", "Low"]

SizeBucket = Literal[
    "1-10", "11-50", "51-200", "201-1000", "1001-5000", "5001+", "unknown"
]

GMVConfidence = Literal["high", "medium", "low"]


@dataclass
class EventHints:
    """User-supplied hints that supplement adapter scraping."""

    conference: str | None = None  # one of Notion's Conference / Trigger options
    event_name: str | None = None
    event_date: date | None = None
    venue: str | None = None
    overlay: str | None = None  # force a specific overlay key (e.g. "apa26")


@dataclass
class EventMeta:
    name: str
    platform: str
    platform_event_id: str
    source_url: str
    venue: str | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass
class RawExhibitor:
    name: str
    booth: str | None = None
    official_description: str | None = None
    website: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    extraction_confidence: Literal["high", "medium", "low"] = "high"


@dataclass
class CompanyProfile:
    """Enriched company record, ready to map to Notion."""

    display_name: str
    name_normalized: str
    industry: NotionIndustry = "Other"
    size_bucket: SizeBucket = "unknown"
    wealth_tier: NotionWealthTier = "❓ SMB / Personal"
    priority: NotionPriority = "Low"
    website: str | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    description: str | None = None
    notes_appendix: str | None = None  # tabmac-flavored extras from overlays
    score: int = 0
    gmv_usd: int | None = None
    gmv_confidence: GMVConfidence | None = None
    gmv_note: str | None = None
    enrichment_sources: dict[str, str] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    raw_exhibitor: RawExhibitor | None = None


@dataclass
class NotionRow:
    """Payload-ready row destined for the Guest CRM data source."""

    company: CompanyProfile
    conference: str | None
    event_date: date | None
    customer_number: int | None = None  # assigned at sink time
