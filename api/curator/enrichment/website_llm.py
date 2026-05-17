"""Firecrawl-backed enricher.

For each company:
1. If the exhibitor record carries a website, scrape that.
2. Otherwise let Firecrawl's extract use its built-in web search.

Firecrawl's /extract endpoint scrapes the source(s) and runs LLM extraction
against a JSON schema in a single call, so we don't need a separate Anthropic
hop.

Results are cached in SQLite (provider = "website_llm", key = normalized name)
to avoid re-billing on a re-run.
"""
from __future__ import annotations

import os
import sys
from typing import Any, get_args

from curator.config import Settings
from curator.enrichment.pipeline import normalize_name
from curator.models import (
    CompanyProfile,
    NotionIndustry,
    NotionWealthTier,
    RawExhibitor,
    SizeBucket,
)
from curator.storage import db as storage_db


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "industry": {
            "type": "string",
            "enum": list(get_args(NotionIndustry)),
            "description": "Pick the single best-fit industry for this company.",
        },
        "size_bucket": {
            "type": "string",
            "enum": list(get_args(SizeBucket)),
            "description": "Approximate global headcount band.",
        },
        "hq_city": {
            "type": "string",
            "description": "City of the company's main headquarters.",
        },
        "hq_country": {
            "type": "string",
            "description": "Country of the company's main headquarters.",
        },
        "short_description": {
            "type": "string",
            "description": "One-sentence description of what the company does.",
        },
        "website": {
            "type": "string",
            "description": "Canonical company website URL, if found.",
        },
        "is_public_company": {"type": "boolean"},
        "is_government_or_nonprofit": {"type": "boolean"},
    },
    "required": ["industry", "size_bucket"],
}


def _size_to_wealth_tier(
    size_bucket: SizeBucket,
    industry: NotionIndustry,
    is_public: bool | None,
    is_govnp: bool | None,
) -> NotionWealthTier:
    if industry == "Education / Research":
        return "🎓 Education / Research"
    if industry == "Government / Non-profit" or is_govnp:
        return "🏛️ Government / Non-profit"
    if industry == "Hospitality / Events":
        return "🤝 Hospitality Partner"
    if size_bucket == "5001+":
        # Distinguish mega-cap vs. large enterprise via public-company hint
        return "💎 Mega Cap" if is_public else "🏢 Large Enterprise"
    if size_bucket in ("1001-5000",):
        return "🏢 Large Enterprise"
    if size_bucket in ("201-1000",):
        return "📈 Mid-Market"
    if size_bucket in ("11-50", "51-200"):
        return "🚀 Funded Startup"
    return "❓ SMB / Personal"


class WebsiteLLMEnricher:
    provider_id = "website_llm"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        api_key = self.settings.firecrawl_api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "website_llm enricher requires FIRECRAWL_API_KEY. "
                "Skip this enricher by removing it from CURATOR_ENRICHERS."
            )
        # Lazy import so users without firecrawl-py installed can still use heuristic.
        from firecrawl import Firecrawl

        self._client = Firecrawl(api_key=api_key)
        self._conn = storage_db.connect(self.settings.db_path)

    def _cache_lookup(self, name_normalized: str) -> dict[str, Any] | None:
        return storage_db.cache_get(self._conn, self.provider_id, name_normalized)

    def _cache_save(self, name_normalized: str, payload: dict[str, Any]) -> None:
        storage_db.cache_put(self._conn, self.provider_id, name_normalized, payload)

    def enrich(
        self, exhibitor: RawExhibitor, profile: CompanyProfile
    ) -> dict[str, Any]:
        name_norm = normalize_name(exhibitor.name)
        cached = self._cache_lookup(name_norm)
        if cached is not None:
            return self._payload_to_update(cached)

        urls = [exhibitor.website] if exhibitor.website else None
        prompt = (
            f"Profile the company {exhibitor.name!r}. "
            "Classify its industry into one of the allowed values and estimate "
            "its size bucket based on the website content. Set "
            "is_government_or_nonprofit=true for government agencies, "
            "departments, foundations, associations, and societies."
        )
        if exhibitor.official_description:
            prompt += f"\n\nOfficial description from the event: {exhibitor.official_description!r}"

        try:
            result = self._client.extract(
                urls=urls,
                prompt=prompt,
                schema=SCHEMA,
                enable_web_search=urls is None,
                timeout=120,
            )
        except Exception as exc:  # firecrawl errors come in many flavors
            print(
                f"[website_llm] extract failed for {exhibitor.name!r}: {exc}",
                file=sys.stderr,
            )
            return {}

        payload = _result_to_dict(result)
        if not payload:
            return {}
        self._cache_save(name_norm, payload)
        return self._payload_to_update(payload)

    def _payload_to_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        industry = payload.get("industry")
        size_bucket: SizeBucket = payload.get("size_bucket") or "unknown"
        if industry not in get_args(NotionIndustry):
            industry = "Other"

        wealth_tier = _size_to_wealth_tier(
            size_bucket=size_bucket,
            industry=industry,
            is_public=payload.get("is_public_company"),
            is_govnp=payload.get("is_government_or_nonprofit"),
        )

        update: dict[str, Any] = {
            "industry": industry,
            "size_bucket": size_bucket,
            "wealth_tier": wealth_tier,
        }
        if payload.get("hq_city"):
            update["hq_city"] = payload["hq_city"]
        if payload.get("hq_country"):
            update["hq_country"] = payload["hq_country"]
        if payload.get("short_description"):
            update["description"] = payload["short_description"]
        if payload.get("website"):
            update["website"] = payload["website"]
        return update


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Firecrawl's SDK returns a typed response object; normalize to dict."""
    if result is None:
        return {}
    if isinstance(result, dict):
        data = result.get("data") or result.get("extract") or result
        return data if isinstance(data, dict) else {}
    # Pydantic-ish model
    for attr in ("data", "extract", "model_dump"):
        value = getattr(result, attr, None)
        if callable(value):
            try:
                dumped = value()
                if isinstance(dumped, dict):
                    return dumped.get("data") or dumped.get("extract") or dumped
            except Exception:
                continue
        elif value is not None:
            if isinstance(value, dict):
                return value
    return {}
