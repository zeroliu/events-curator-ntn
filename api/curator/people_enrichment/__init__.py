"""Contact enrichment: given a company name, find the person most likely to handle event organization.

Ported from the standalone TypeScript CRM_enricher project. Two-tier pipeline:
Apollo (paid, structured) first, Claude Agent SDK with WebSearch as fallback.
"""
from __future__ import annotations

from curator.people_enrichment.models import ResearchResult
from curator.people_enrichment.pipeline import (
    enrich_company_contact,
    prefetch_and_store_contacts,
)

__all__ = ["ResearchResult", "enrich_company_contact", "prefetch_and_store_contacts"]
