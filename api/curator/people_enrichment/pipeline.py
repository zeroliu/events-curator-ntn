from __future__ import annotations

import asyncio
import logging

from curator.config import Settings
from curator.people_enrichment.apollo import apollo_lookup
from curator.people_enrichment.llm import claude_research
from curator.people_enrichment.models import ResearchResult

log = logging.getLogger(__name__)


async def enrich_company_contact(company_name: str, settings: Settings) -> ResearchResult:
    """Apollo first (if configured), Claude Agent SDK + WebSearch otherwise.
    Raises RuntimeError when no usable provider is available."""
    if settings.apollo_api_key:
        result = await asyncio.to_thread(apollo_lookup, company_name, settings.apollo_api_key)
        if result is not None:
            return result
        log.info("[enrich] Apollo returned nothing for %r, falling back to Claude", company_name)

    try:
        return await claude_research(company_name)
    except Exception as exc:  # CLI missing, not signed in, etc.
        raise RuntimeError(f"Claude Agent SDK call failed for {company_name!r}: {exc}") from exc
