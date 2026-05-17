from __future__ import annotations

import re
from typing import Iterable

from curator.enrichment.base import CompanyEnricher
from curator.enrichment.heuristic import HeuristicEnricher
from curator.models import CompanyProfile, RawExhibitor

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    return _NORMALIZE_RE.sub(" ", name.lower()).strip()


def build_default_enrichers(
    provider_ids: list[str],
    *,
    prefetched_agent: dict[str, dict] | None = None,
) -> list[CompanyEnricher]:
    enrichers: list[CompanyEnricher] = []
    for pid in provider_ids:
        if pid == "heuristic":
            enrichers.append(HeuristicEnricher())
        elif pid == "website_llm":
            from curator.enrichment.website_llm import WebsiteLLMEnricher

            enrichers.append(WebsiteLLMEnricher())
        elif pid == "apollo":
            from curator.enrichment.apollo import ApolloEnricher

            enrichers.append(ApolloEnricher())
        elif pid == "agent_enricher":
            from curator.enrichment.agent_enricher import AgentEnricher

            enrichers.append(AgentEnricher(prefetched_agent or {}))
        else:
            raise ValueError(f"unknown enricher id: {pid}")
    return enrichers


_PROFILE_FIELDS = {
    "industry",
    "size_bucket",
    "wealth_tier",
    "priority",
    "website",
    "hq_city",
    "hq_country",
    "description",
    "notes_appendix",
    "score",
    "gmv_usd",
    "gmv_confidence",
    "gmv_note",
}


def run_enrichers(
    exhibitor: RawExhibitor,
    enrichers: Iterable[CompanyEnricher],
    overlay: CompanyEnricher | None,
) -> CompanyProfile:
    profile = CompanyProfile(
        display_name=exhibitor.name,
        name_normalized=normalize_name(exhibitor.name),
        raw_exhibitor=exhibitor,
    )

    chain: list[CompanyEnricher] = list(enrichers)
    if overlay is not None:
        chain.append(overlay)

    for enricher in chain:
        update = enricher.enrich(exhibitor, profile)
        if not update:
            continue

        # Merge `extras` separately so overlays can layer.
        extras_update = update.get("extras")
        if isinstance(extras_update, dict):
            profile.extras.update(extras_update)

        for field_name in _PROFILE_FIELDS:
            if field_name not in update:
                continue
            value = update[field_name]
            if value in (None, ""):
                continue
            # Last writer wins for profile fields (overlay applied last).
            setattr(profile, field_name, value)
            profile.enrichment_sources[field_name] = enricher.provider_id

    return profile
