"""Apollo two-step contact lookup. Ported from CRM_enricher/src/enrichers/apollo.ts."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from curator.people_enrichment.models import ResearchResult

log = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/api/v1"

PRIORITY_TITLES: list[str] = [
    "Administrative Business Partner",
    "Executive Assistant to CEO",
    "Executive Assistant to the CEO",
    "Director of Events",
    "Director, Meetings and Events",
    "Director, Meetings & Events",
    "Director Meetings and Events",
    "Director of Meetings and Events",
    "Manager, Meetings and Events",
    "Manager of Meetings and Events",
    "Events Manager",
    "Meetings Manager",
    "Head of Events",
    "Senior Events Manager",
    "Senior Meeting Planner",
    "Meeting Planner",
    "Event Coordinator",
    "Events Coordinator",
    "Conference Manager",
]

FALLBACK_TITLES: list[str] = [
    "Chief of Staff",
    "Chief Operating Officer",
    "COO",
    "Chief Executive Officer",
    "CEO",
    "Founder",
    "Co-Founder",
    "Owner",
    "General Manager",
    "President",
]


def apollo_lookup(company_name: str, api_key: str) -> ResearchResult | None:
    """Two-step Apollo flow. Returns None when nothing usable is found, so the
    caller can fall back to the LLM path."""
    with httpx.Client(timeout=20.0) as client:
        candidate = _search_candidate(client, api_key, company_name, PRIORITY_TITLES, "priority")
        if candidate is None:
            candidate = _search_candidate(
                client, api_key, company_name, FALLBACK_TITLES, "fallback"
            )
        if candidate is None:
            log.info("[apollo] no match for %r in either title tier", company_name)
            return None

        enriched = _enrich_person(client, api_key, candidate["id"])
        if enriched is None:
            log.info("[apollo] enrichment failed for candidate %s, skipping", candidate["id"])
            return None

        return _to_research_result(enriched)


def _search_candidate(
    client: httpx.Client,
    api_key: str,
    company_name: str,
    titles: list[str],
    tier: str,
) -> dict[str, Any] | None:
    resp = client.post(
        f"{APOLLO_BASE}/mixed_people/api_search",
        headers={
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        },
        json={
            "q_organization_name": company_name,
            "person_titles": titles,
            "page": 1,
            "per_page": 5,
        },
    )
    if resp.status_code >= 400:
        log.error("[apollo] search %s failed %s: %s", tier, resp.status_code, resp.text[:500])
        return None

    people = (resp.json() or {}).get("people") or []
    if not people:
        return None

    # Prefer candidates Apollo says have a reachable email; among those, prefer
    # titles that substring-match one of our query titles.
    with_email = [p for p in people if p.get("has_email")]
    pool = with_email if with_email else people
    lowered = [t.lower() for t in titles]
    exact = next(
        (
            p
            for p in pool
            if isinstance(p.get("title"), str)
            and any(t in p["title"].lower() for t in lowered)
        ),
        None,
    )
    chosen = exact if exact is not None else pool[0]
    log.info(
        "[apollo] %s-tier candidate at %r: %s %s — %s (id=%s, has_email=%s)",
        tier,
        company_name,
        chosen.get("first_name") or "?",
        chosen.get("last_name_obfuscated") or "?",
        chosen.get("title") or "<no title>",
        chosen.get("id"),
        chosen.get("has_email"),
    )
    return chosen


def _enrich_person(client: httpx.Client, api_key: str, person_id: str) -> dict[str, Any] | None:
    resp = client.post(
        f"{APOLLO_BASE}/people/match",
        headers={
            "X-Api-Key": api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        },
        json={"id": person_id, "reveal_personal_emails": True},
    )
    if resp.status_code >= 400:
        log.error("[apollo] enrich failed %s: %s", resp.status_code, resp.text[:500])
        return None
    return (resp.json() or {}).get("person")


def _to_research_result(person: dict[str, Any]) -> ResearchResult:
    phones = person.get("phone_numbers") or []
    phone = None
    if phones:
        phone = phones[0].get("sanitized_number") or phones[0].get("raw_number")

    sources: list[str] = [f"apollo:{person.get('id')}"]
    if person.get("linkedin_url"):
        sources.append(person["linkedin_url"])

    name = person.get("name") or _join_name(person.get("first_name"), person.get("last_name"))
    org = (person.get("organization") or {}).get("name") or "<no org>"
    title = person.get("title")
    email = person.get("email")

    return ResearchResult(
        person_name=name,
        title=title,
        email=email,
        phone=phone,
        sources=sources,
        confidence="high" if email else "medium",
        reasoning=f"Apollo match: {name or '<no name>'} — {title or '<no title>'} at {org}.",
        provider="apollo",
    )


def _join_name(first: str | None, last: str | None) -> str | None:
    parts = [p for p in (first, last) if isinstance(p, str) and p.strip()]
    return " ".join(parts) if parts else None
