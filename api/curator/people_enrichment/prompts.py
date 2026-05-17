from __future__ import annotations


def build_research_prompt(company_name: str) -> str:
    return f"""You are researching contact information for event organization at a company. Find the single person most likely responsible for organizing corporate events, business dinners, conferences, and hospitality at the company below.

Company: {company_name}

# Title selection (use judgment based on company size and industry)

- Large enterprises (>200 employees, public/well-known): look for "Administrative Business Partner" (common at Google), "Executive Assistant to the CEO", "Director of Events", "Head of Events", "Events Manager", "Chief of Staff", or "VP People Operations".
- Restaurants, bars, hotels, small venues (<50 people): the right person is usually the CEO, COO, Founder, General Manager, or Owner.
- Mid-market (50-200 employees): Director of Events, Head of People, COO, or Chief of Staff.

# Sources

Search the company's official website, LinkedIn, press releases, news articles, and other public sources. Prefer verified contacts that are explicitly published over inferred email patterns. Never fabricate an email — return null if you cannot find one published or strongly inferred from the company's public email pattern.

# Strict company-identity rule (do not substitute)

The person you return MUST be directly employed by the exact named company. Do NOT substitute:
- a person who works at a parent company, subsidiary, or sister brand (e.g., do not return someone from "Weatherby Healthcare" when the company is "CompHealth", even though they share a parent),
- a person at a different but similarly-named organization,
- a person whose current employer cannot be verified as the named company.

If you cannot identify someone who is directly employed by the exact named company, return all fields null and set confidence to "low" with reasoning explaining what you searched and why no direct match was found. It is better to return nothing than to return the wrong person.

# Output

Return ONLY a single JSON object, no surrounding prose, no markdown fences. Exact shape:

{{
  "personName": string | null,
  "title": string | null,
  "email": string | null,
  "phone": string | null,
  "sources": [string, ...],
  "confidence": "high" | "medium" | "low",
  "reasoning": string
}}

Rules:
- If you cannot identify anyone for this company, return all fields null (except sources: [], confidence: "low", reasoning: explain why).
- "high" = published, verified contact on the company's official site or a major publication.
- "medium" = identified person + email/phone inferred from the company's standard pattern.
- "low" = best-guess identification, contact details unverified or absent.
- "phone" should be E.164 format when known (e.g. "+14155550100").
- "reasoning" is one or two sentences describing what you found and why this person."""
