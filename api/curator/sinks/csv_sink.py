"""CSV sink. Reproduces the legacy outputs/apa26_tabmac_exhibitor_outreach.csv
columns when APA26 overlay is in play; otherwise emits a generic schema.
"""
from __future__ import annotations

import csv
from pathlib import Path

from curator.models import EventMeta, NotionRow
from curator.sinks.base import SinkResult


LEGACY_FIELDNAMES = [
    "company",
    "booth",
    "official_description",
    "likely_segment",
    "tabmac_relevance",
    "outreach_priority",
    "why_contact",
    "suggested_pitch_angle",
]


GENERIC_FIELDNAMES = [
    "company",
    "booth",
    "official_description",
    "industry",
    "wealth_tier",
    "priority",
    "website",
    "notes_appendix",
]


class CSVSink:
    sink_id = "csv"

    def __init__(self, output_path: Path, *, legacy: bool = True) -> None:
        self.output_path = output_path
        self.legacy = legacy

    def write(self, event: EventMeta, rows: list[NotionRow]) -> SinkResult:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = LEGACY_FIELDNAMES if self.legacy else GENERIC_FIELDNAMES
        with self.output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(self._serialize(row))
        return SinkResult(created=len(rows))

    def _serialize(self, row: NotionRow) -> dict[str, str]:
        company = row.company
        raw = company.raw_exhibitor
        if self.legacy:
            extras = company.extras
            return {
                "company": company.display_name,
                "booth": (raw.booth if raw else "") or "",
                "official_description": (raw.official_description if raw else "") or "",
                "likely_segment": extras.get("legacy_segment", ""),
                "tabmac_relevance": extras.get("tabmac_relevance", ""),
                "outreach_priority": _legacy_priority(company.priority),
                "why_contact": extras.get("why_contact", ""),
                "suggested_pitch_angle": extras.get("suggested_pitch_angle", ""),
            }
        return {
            "company": company.display_name,
            "booth": (raw.booth if raw else "") or "",
            "official_description": (raw.official_description if raw else "") or "",
            "industry": company.industry,
            "wealth_tier": company.wealth_tier,
            "priority": company.priority,
            "website": company.website or "",
            "notes_appendix": company.notes_appendix or "",
        }


def _legacy_priority(priority: str) -> str:
    # Legacy CSV used "Medium"; internal model uses Notion's "Mid".
    return {"High": "High", "Mid": "Medium", "Low": "Low"}.get(priority, priority)
