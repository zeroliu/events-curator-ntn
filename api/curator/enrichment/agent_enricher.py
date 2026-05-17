"""Claude Agent SDK enricher.

Replaces the regex-based heuristic with `claude-haiku-4-5` + WebSearch.
Companies are pre-fetched in batches of 20 by `prefetch_agent_results`; the
sync `AgentEnricher.enrich` is a pure dict lookup so it slots into the
existing per-exhibitor `run_enrichers` loop without touching merge logic.

Like `people_enrichment/llm.py`, this uses the locally-installed Claude Code
CLI credentials — no API key is read from this codebase.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, get_args

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from curator.config import Settings
from curator.enrichment.pipeline import normalize_name
from curator.models import (
    CompanyProfile,
    GMVConfidence,
    NotionIndustry,
    NotionPriority,
    NotionWealthTier,
    RawExhibitor,
    SizeBucket,
)
from curator.storage import db as storage_db

log = logging.getLogger(__name__)

BATCH_SIZE = 20
CACHE_PROVIDER = "agent_enricher"
MODEL_ID = "claude-haiku-4-5"

_INDUSTRY_VALUES = list(get_args(NotionIndustry))
_SIZE_VALUES = list(get_args(SizeBucket))
_WEALTH_VALUES = list(get_args(NotionWealthTier))
_PRIORITY_VALUES = list(get_args(NotionPriority))
_GMV_CONF_VALUES = list(get_args(GMVConfidence))
# `confidence` and `gmv_confidence` share the same high/medium/low scale; alias
# so the schema slot reads as intent rather than a coincidence.
_CONFIDENCE_VALUES = _GMV_CONF_VALUES

BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_normalized": {"type": "string"},
                    "industry": {"type": "string", "enum": _INDUSTRY_VALUES},
                    "size_bucket": {"type": "string", "enum": _SIZE_VALUES},
                    "wealth_tier": {"type": "string", "enum": _WEALTH_VALUES},
                    "priority": {"type": "string", "enum": _PRIORITY_VALUES},
                    "website": {"type": ["string", "null"]},
                    "hq_city": {"type": ["string", "null"]},
                    "hq_country": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "gmv_usd": {"type": ["integer", "null"]},
                    "gmv_confidence": {"type": "string", "enum": _GMV_CONF_VALUES},
                    "gmv_note": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": _CONFIDENCE_VALUES},
                },
                "required": [
                    "name_normalized",
                    "industry",
                    "size_bucket",
                    "wealth_tier",
                    "priority",
                    "gmv_confidence",
                    "confidence",
                    "sources",
                ],
            },
        },
    },
    "required": ["results"],
}


def _build_batch_prompt(batch: list[RawExhibitor]) -> str:
    rows: list[dict[str, Any]] = []
    for exhibitor in batch:
        rows.append(
            {
                "name_normalized": normalize_name(exhibitor.name),
                "display_name": exhibitor.name,
                "booth": exhibitor.booth,
                "official_description": exhibitor.official_description,
                "website": exhibitor.website,
            }
        )

    return f"""You are enriching exhibitor records for an event-CRM pipeline. For each company below, use WebSearch to gather public information, then output a structured record.

Required for every company:
- `name_normalized`: echo the input value verbatim (we use it to map your output back to our records).
- `industry`: pick the single best fit from this exact list (no other strings allowed): {_INDUSTRY_VALUES}.
- `size_bucket`: employee count band, choose from: {_SIZE_VALUES}.
- `wealth_tier`: commercial scale signal, choose from: {_WEALTH_VALUES}. Use "🎓 Education / Research" for universities/research institutes, "🏛️ Government / Non-profit" for public entities and registered nonprofits, "🤝 Hospitality Partner" for hotels/event venues/destination management, "💎 Mega Cap" for >$200B market cap, "🏢 Large Enterprise" for $10B-$200B, "📈 Mid-Market" for ~$100M-$10B, "🚀 Funded Startup" for VC-backed under $100M, and "❓ SMB / Personal" only when nothing else fits.
- `priority`: "High" / "Mid" / "Low" — guess the partnership relevance for someone selling premium B2B services. Public mega-cap and large enterprise = High by default; SMB and government = Low; everything else Mid.
- `website`, `hq_city`, `hq_country`, `description`: best public values, or null if unknown. `description` should be 1-2 sentences in your own words.
- `gmv_usd`: best public estimate of annual Gross Merchandise Volume / revenue / transactions-volume proxy, in US dollars as a single integer (e.g. 5000000000 for $5B). If the company is non-commercial (university, government, nonprofit) set to null. If unknown set to null.
- `gmv_confidence`: "high" if you found an official disclosure with year, "medium" if reputable third-party estimate, "low" if order-of-magnitude guess or N/A.
- `gmv_note`: short citation/context, e.g. "FY2024 10-K: $5.1B revenue" or "Not applicable — public university" or null.
- `sources`: array of URLs you actually consulted via WebSearch.
- `confidence`: overall "high"/"medium"/"low" for the whole record.

Be conservative: prefer null over hallucination. Do not invent numbers. If WebSearch returns nothing useful for a company, still emit the record with null fields and confidence="low".

Companies to enrich (JSON):
{json.dumps(rows, ensure_ascii=False, indent=2)}

Return a single JSON object matching the required schema, with one entry in `results` per company above, in the same order."""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def _research_batch(batch: list[RawExhibitor]) -> dict[str, dict[str, Any]]:
    """Run one Agent SDK query for up to BATCH_SIZE companies; return a
    `{name_normalized: result}` map. Missing entries are silently dropped."""
    options = ClaudeAgentOptions(
        model=MODEL_ID,
        allowed_tools=["WebSearch"],
        output_format={"type": "json_schema", "schema": BATCH_SCHEMA},
    )

    structured: dict[str, Any] | None = None
    last_text: str = ""
    async for msg in query(prompt=_build_batch_prompt(batch), options=options):
        if isinstance(msg, ResultMessage):
            structured = getattr(msg, "structured_output", None)
            break
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    last_text = block.text

    payload = structured if structured is not None else _extract_json_object(last_text)
    if payload is None:
        log.error(
            "[agent_enricher] no parseable JSON for batch of %d. raw=%r",
            len(batch),
            last_text[:500],
        )
        return {}

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        log.error("[agent_enricher] payload has no `results` array: %r", payload)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for entry in results:
        if not isinstance(entry, dict):
            continue
        key = entry.get("name_normalized")
        if isinstance(key, str) and key:
            out[key] = entry
    return out


async def prefetch_agent_results(
    exhibitors: list[RawExhibitor],
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    """Cache-aware batched fetch. Returns `{name_normalized: structured_record}`.

    Looks up `enrichment_cache(provider="agent_enricher")` first; only cache
    misses are sent through the Agent SDK in batches of BATCH_SIZE, sequentially.
    With `force_refresh=True`, every company is treated as a miss but fresh
    results still write through to the cache.
    """
    if not exhibitors:
        return {}

    conn = storage_db.connect(settings.db_path)
    try:
        results: dict[str, dict[str, Any]] = {}
        misses: list[RawExhibitor] = []
        seen: set[str] = set()
        for exhibitor in exhibitors:
            key = normalize_name(exhibitor.name)
            if key in seen:
                continue
            seen.add(key)
            cached = (
                None if force_refresh else storage_db.cache_get(conn, CACHE_PROVIDER, key)
            )
            if cached is not None:
                results[key] = cached
                log.info("[agent_enricher] cache hit %s", key)
            else:
                misses.append(exhibitor)

        for i in range(0, len(misses), BATCH_SIZE):
            batch = misses[i : i + BATCH_SIZE]
            log.info(
                "[agent_enricher] batch %d/%d (%d companies)",
                i // BATCH_SIZE + 1,
                (len(misses) + BATCH_SIZE - 1) // BATCH_SIZE,
                len(batch),
            )
            batch_out = await _research_batch(batch)
            for exhibitor in batch:
                key = normalize_name(exhibitor.name)
                record = batch_out.get(key)
                if record is None:
                    log.warning("[agent_enricher] no result for %s", key)
                    continue
                storage_db.cache_put(conn, CACHE_PROVIDER, key, record)
                results[key] = record
        return results
    finally:
        conn.close()


class AgentEnricher:
    provider_id = "agent_enricher"

    _CARRY_KEYS: tuple[str, ...] = (
        "industry",
        "size_bucket",
        "wealth_tier",
        "priority",
        "website",
        "hq_city",
        "hq_country",
        "description",
        "gmv_usd",
        "gmv_confidence",
        "gmv_note",
    )

    def __init__(self, prefetched: dict[str, dict[str, Any]]) -> None:
        self._results = prefetched

    def enrich(
        self, exhibitor: RawExhibitor, profile: CompanyProfile
    ) -> dict[str, Any]:
        record = self._results.get(profile.name_normalized)
        if not record:
            return {}
        out: dict[str, Any] = {}
        for key in self._CARRY_KEYS:
            value = record.get(key)
            if value in (None, ""):
                continue
            out[key] = value
        return out


def run_prefetch_sync(
    exhibitors: list[RawExhibitor],
    settings: Settings,
    *,
    force_refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    """Sync wrapper used by the FastAPI request path (which is sync today)."""
    return asyncio.run(
        prefetch_agent_results(exhibitors, settings, force_refresh=force_refresh)
    )
