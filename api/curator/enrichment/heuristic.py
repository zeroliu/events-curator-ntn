"""Generic classifier mapped to the Notion 'Industry' select options.

The 11 Notion Industry buckets (Tech / Software, Healthcare / Pharma, ...) are
deliberately coarse. Per-event overlays add finer-grained classification and
priority signals on top of this baseline.
"""
from __future__ import annotations

import re
from typing import Any

from curator.models import CompanyProfile, NotionIndustry, RawExhibitor

# Order matters: first match wins, so place more specific rules first.
_INDUSTRY_RULES: list[tuple[NotionIndustry, re.Pattern[str]]] = [
    (
        "Healthcare / Pharma",
        re.compile(
            r"\bpharma|pharmaceutical|therapeutics|biotech|biosciences|biopharma|"
            r"\bdrug|medicines|\bclinic\b|clinical|hospital|medical|health system|"
            r"\bEHR\b|telehealth|psychiatric|behavioral health|psychotherapy|"
            r"medical device|neuromodulation|\bTMS\b|\bECT\b|locum|locums|"
            r"healthcare|nurs(e|ing)|physician|patient",
            re.IGNORECASE,
        ),
    ),
    (
        "Finance / VC",
        re.compile(
            r"\bbank\b|\binsurance\b|\bcapital\b|\bventures?\b|\bfund\b|"
            r"\bequity\b|asset management|wealth|fintech|payments|brokerage|trading|"
            r"private equity|hedge fund",
            re.IGNORECASE,
        ),
    ),
    (
        "Legal",
        re.compile(
            r"\bLLP\b|\battorneys?\b|\blaw\s+(group|firm|office|partners)\b|legal services",
            re.IGNORECASE,
        ),
    ),
    (
        "Consulting",
        re.compile(
            r"\bconsult(ing|ants?)\b|\badvisory\b|McKinsey|\bBain\b|\bBCG\b|Deloitte|Accenture|PwC",
            re.IGNORECASE,
        ),
    ),
    (
        "Education / Research",
        re.compile(
            r"\buniversity\b|\bcollege\b|\binstitute\b|research center|"
            r"\bacademy\b|\bjournal\b|university press|publishing|publisher|"
            r"\bCME\b|continuing education|fellowship|residency",
            re.IGNORECASE,
        ),
    ),
    (
        "Government / Non-profit",
        re.compile(
            r"\bdepartment\b|\bbureau\b|\bcounty\b|\bstate\b|\bfederal\b|"
            r"\barmy\b|\bnavy\b|\bair force\b|veterans|\bVA\b|\bDoD\b|"
            r"\bfoundation\b|\bassociation\b|\bsociety\b|nonprofit|not-for-profit|"
            r"\bconsortium\b|advocacy|ministry",
            re.IGNORECASE,
        ),
    ),
    (
        "Hospitality / Events",
        re.compile(
            r"\bhotel\b|hospitality|catering|event production|venue|destination management|"
            r"\bresort\b|conference services",
            re.IGNORECASE,
        ),
    ),
    (
        "Gaming / Entertainment",
        re.compile(
            r"\bgames?\b|gaming|esports|\bstudios?\b|entertainment|media production|"
            r"streaming|animation",
            re.IGNORECASE,
        ),
    ),
    (
        "Real Estate",
        re.compile(
            r"real estate|\bproperties\b|\bREIT\b|brokerage|leasing|property management",
            re.IGNORECASE,
        ),
    ),
    (
        "Tech / Software",
        re.compile(
            r"\bsoftware\b|\bplatform\b|\bSaaS\b|\bAI\b|\bML\b|machine learning|"
            r"\bcloud\b|\bAPI\b|developer|cybersecurity|\bDevOps\b|infrastructure|"
            r"\bdatabase\b|analytics|automation|\bSDK\b|app developer|technology|"
            r"data engineering|generative AI",
            re.IGNORECASE,
        ),
    ),
]


_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", value or "").strip()


def classify_industry(name: str, description: str | None) -> NotionIndustry:
    haystack = f"{name}\n{description or ''}"
    for industry, pattern in _INDUSTRY_RULES:
        if pattern.search(haystack):
            return industry
    return "Other"


def baseline_wealth_tier(industry: NotionIndustry):
    """Conservative wealth-tier guess from industry alone.

    Used when no size signal is available. ``website_llm`` / ``apollo`` enrichers
    refine this with actual headcount.
    """
    if industry == "Education / Research":
        return "🎓 Education / Research"
    if industry == "Government / Non-profit":
        return "🏛️ Government / Non-profit"
    if industry == "Hospitality / Events":
        return "🤝 Hospitality Partner"
    return "❓ SMB / Personal"


class HeuristicEnricher:
    provider_id = "heuristic"

    def enrich(
        self, exhibitor: RawExhibitor, profile: CompanyProfile
    ) -> dict[str, Any]:
        industry = classify_industry(exhibitor.name, exhibitor.official_description)
        out: dict[str, Any] = {"industry": industry}

        # Only set wealth_tier if it's still the default — overlays/paid enrichers
        # take precedence.
        if profile.wealth_tier == "❓ SMB / Personal":
            out["wealth_tier"] = baseline_wealth_tier(industry)

        # Generic priority: very weak signal. Long description + named brand =
        # mid; otherwise low. Overlays will override.
        desc = exhibitor.official_description or ""
        if profile.priority == "Low":
            if len(desc) >= 250 and exhibitor.booth and "KIOSK" not in exhibitor.booth.upper():
                out["priority"] = "Mid"

        # Carry website / description forward if discovery surfaced them.
        if exhibitor.website and not profile.website:
            out["website"] = exhibitor.website
        if exhibitor.official_description and not profile.description:
            out["description"] = exhibitor.official_description
        return out
