"""APA 2026 overlay.

Ports the APA-specific classifier from curate_apa26_exhibitors.py:14-241.
The legacy script emitted 14 hospitality-flavored segments; this overlay maps
each one to a Notion 'Industry' value and preserves the legacy segment +
Tabmac pitch language in ``CompanyProfile.extras`` so the CSV sink can
reproduce the original output for regression.
"""
from __future__ import annotations

import re
from typing import Any

from curator.models import (
    CompanyProfile,
    NotionIndustry,
    NotionPriority,
    RawExhibitor,
)


SEGMENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "Government/public-sector recruiting",
        re.compile(
            r"Department|Bureau|Veterans|\bArmy\b|\bNavy\b|Correctional|County|Province|"
            r"Chickasaw|\bVA\b|\bDoD\b|State Hospitals|UCSF|University of Texas|OU Health|UW Psychiatry",
            re.I,
        ),
    ),
    (
        "Healthcare staffing/recruiting",
        re.compile(
            r"staffing|locum|locums|recruit|PracticeLink|Weatherby|CompHealth|Medicus|"
            r"Jackson and Coker|Monroe|NZDr|Astrya|Global Medical Staffing",
            re.I,
        ),
    ),
    (
        "Neuromodulation/medical device",
        re.compile(
            r"\bTMS\b|\bECT\b|neuromodulation|stimulation|device|bioelectronic|light therapy|"
            r"focused ultrasound|MagVenture|NeuroStar|Magnus|Soterix|Somatics|SigmaStim|"
            r"Flow Neuroscience|Sonomind|Electromedical",
            re.I,
        ),
    ),
    (
        "Pharma/biotech",
        re.compile(
            r"pharma|pharmaceutical|therapeutics|biosciences|biopharma|medicines|drug development|"
            r"Zurzuvae|AbbVie|Janssen|Johnson & Johnson|Lilly|Neurocrine|Axsome|Teva|Vanda|Zevra|"
            r"Bristol Myers|Collegium|OWP|Vertical",
            re.I,
        ),
    ),
    (
        "Healthtech/EHR/practice software",
        re.compile(
            r"\bEHR\b|software|platform|\bAI\b|scribe|billing|\bRCM\b|practice management|telehealth|"
            r"documentation|workflow|intake|Valant|AdvancedMD|CharmHealth|mdhub|Heidi|MindBill|"
            r"PracticeQ|Nanonets|NoBackOffice|BastionGPT|Zenara|Saffron",
            re.I,
        ),
    ),
    (
        "Clinical assessment/digital therapeutics",
        re.compile(
            r"assessment|screen|measurement|digital mental health|pharmacogenomic|GeneSight|"
            r"MindMetrix|CNS Vital Signs|TD Screen|Psynk|PsychNow|ReliefAI|Daybreak|Lumos|Lucimed",
            re.I,
        ),
    ),
    (
        "Research/CRO",
        re.compile(r"\bCRO\b|clinical trials|research center|Julius Clinical|Acacia Research", re.I),
    ),
    (
        "Education/CME/publishing",
        re.compile(
            r"education|CME|university press|publisher|publications|review|training|residency|"
            r"fellowship|board|Beat the Boards|Rosh|Oxford University Press|Cambridge University Press|"
            r"Springer|Wolters Kluwer|JMIR|MDPI|Tmind|Psychiatry Redefined|Zen Psychiatry",
            re.I,
        ),
    ),
    (
        "Association/nonprofit",
        re.compile(
            r"association|society|foundation|consortium|nonprofit|not-for-profit|advocacy|"
            r"Physicians for a National Health Program|Postpartum Support|Catatonia|Clinical TMS Society|"
            r"Christian Medical",
            re.I,
        ),
    ),
    (
        "Practice services/marketing",
        re.compile(
            r"marketing|website|medical-legal|evaluators|insurance|liability|revenue optimization|"
            r"coding|APM BILLING|Doctor Multimedia|American Professional Agency|FC Billing|"
            r"Prime Medical|Sound Medical|Veterans Evaluation",
            re.I,
        ),
    ),
    (
        "Wellness/coaching",
        re.compile(
            r"wellness|coaching|retreat|mindfulness|omega-3|CBD|Emotioncubes|Pause & Presence|OmegaBrite",
            re.I,
        ),
    ),
    (
        "Behavioral health treatment network",
        re.compile(
            r"behavioral health|mental health care|psychiatric care|treatment center|residential|"
            r"eating disorder|substance use|therapy|Talkiatry|Mindpath|Serenity|Sheppard Pratt|"
            r"Rogers|Sierra Tucson|Telecare|Evolve|Equip|ERC Pathlight|Homewood|Austen Riggs|"
            r"PsychPlus|Bay Psychiatric|Brain Health USA|New U Therapy",
            re.I,
        ),
    ),
    (
        "Health system/provider network",
        re.compile(
            r"health system|hospital|medical group|healthcare provider|Kaiser|Cleveland Clinic|"
            r"Northwell|Sutter|PeaceHealth|Atrium|RWJ|Northeast Georgia|McLean|Johns Hopkins|"
            r"Premise|Vituity|Enloe",
            re.I,
        ),
    ),
]

HIGH_NAME_PATTERNS = re.compile(
    r"AbbVie|Acadia Pharmaceuticals|AdvancedMD|Amergis|ARC Health|Atrium Health|Axsome|"
    r"Beacon Behavioral|Biogen|Bristol Myers|CharmHealth|Cleveland Clinic|CompHealth|Cross Country|"
    r"Eli Lilly|ERC Pathlight|Global Medical Staffing|Harmony Biosciences|Integrated Psychiatric Consultants|"
    r"Jackson and Coker|Johnson & Johnson|Kaiser Permanente|LocumTenens|Luye Pharma|Magnus Medical|"
    r"MagVenture|Medicus|Mindpath|Neurocrine|NeuroStar|Northwell|Optum|OWP Pharmaceuticals|"
    r"PracticeLink|Premise Health|PsychPlus|Rogers Behavioral|RWJ|Serenity|Sheppard Pratt|"
    r"Sierra Tucson|SonderMind|Soterix|Sutter Health|Talkiatry|Teva|Universal Health Services|"
    r"Valant|Vanda|Vituity|Weatherby|Zevra",
    re.I,
)

LOW_NAME_PATTERNS = re.compile(
    r"APA Test|Department|Bureau|Veterans Health Administration|Army|Navy|Correctional|County|"
    r"Province|Chickasaw|Physicians for a National|Christian Medical|Catatonia Foundation|"
    r"Epilepsy & Pregnancy|World Sleep Society|Psychology Times|UCSF|University of Texas|"
    r"OU Health|UW Psychiatry",
    re.I,
)

TOP_TARGETS = [
    "AbbVie",
    "Johnson & Johnson",
    "Eli Lilly and Company",
    "Bristol Myers Squibb Company",
    "Neurocrine Biosciences, Inc.",
    "Axsome Therapeutics Inc.",
    "Teva Pharmaceuticals",
    "Universal Health Services Inc.",
    "Kaiser Permanente",
    "Optum",
    "Northwell Health",
    "Cleveland Clinic",
    "Sutter Health",
    "Talkiatry",
    "ARC Health",
    "Mindpath Health",
    "Serenity Mental Health Centers",
    "Sheppard Pratt",
    "Rogers Behavioral Health",
    "CompHealth",
]

NAME_SEGMENT_OVERRIDES: dict[str, str] = {
    "Universal Health Services Inc.": "Health system/provider network",
    "Kaiser Permanente": "Health system/provider network",
    "Cleveland Clinic": "Health system/provider network",
    "Serenity Mental Health Centers": "Behavioral health treatment network",
    "Sheppard Pratt": "Behavioral health treatment network",
    "Rogers Behavioral Health": "Behavioral health treatment network",
    "The Menninger Clinic": "Behavioral health treatment network",
    "Homewood Health": "Behavioral health treatment network",
    "Brain Health USA": "Behavioral health treatment network",
    "Johns Hopkins Healthcare Solutions": "Healthtech/EHR/practice software",
    "Prime Medical Evaluators": "Practice services/marketing",
    "Sound Medical Evaluators, Inc.": "Practice services/marketing",
    "Veterans Evaluation Services": "Practice services/marketing",
    "Zen Psychiatry": "Education/CME/publishing",
    "Psychiatry Redefined": "Education/CME/publishing",
    "the Saffron Solution": "Healthtech/EHR/practice software",
    "Zenara Health": "Healthtech/EHR/practice software",
    "Lucimed": "Neuromodulation/medical device",
    "Lumos Health Inc.": "Neuromodulation/medical device",
    "Daybreak": "Clinical assessment/digital therapeutics",
    "Neurocare Group America, Inc.": "Neuromodulation/medical device",
    "NIBBOT INTERNATIONAL": "Neuromodulation/medical device",
    "Clinical TMS Society": "Association/nonprofit",
    "Cambridge University Press": "Education/CME/publishing",
    "Oxford University Press": "Education/CME/publishing",
    "Springer Nature": "Education/CME/publishing",
    "MDPI": "Education/CME/publishing",
    "JMIR Publications": "Education/CME/publishing",
    "Wolters Kluwer Health": "Education/CME/publishing",
    "American Board of Psychiatry and Neurology, Inc.": "Education/CME/publishing",
    "Postpartum Support International": "Association/nonprofit",
    "World Sleep Society": "Association/nonprofit",
    "The Catatonia Foundation": "Association/nonprofit",
    "Epilepsy & Pregnancy Medical Consortium": "Association/nonprofit",
    "Physicians for a National Health Program": "Association/nonprofit",
    "Pause & Presence Coaching & Retreats": "Wellness/coaching",
    "OmegaBrite Bioscience": "Wellness/coaching",
    "Emotioncubes": "Wellness/coaching",
}

SEGMENT_PITCH: dict[str, tuple[str, str]] = {
    "Healthcare staffing/recruiting": (
        "Recruiting firms use APA for candidate and client conversations.",
        "Offer private dining and near-Moscone options for recruiter-candidate dinners, client meals, and consultant team gatherings.",
    ),
    "Pharma/biotech": (
        "Commercial or medical-affairs exhibitors often bring field teams and meet clinicians, KOLs, or partners during the meeting.",
        "Position Tabmac as a compliant restaurant concierge for HCP/KOL dinners, medical-affairs team meals, and private dining near Moscone.",
    ),
    "Health system/provider network": (
        "Large care organizations commonly bring recruiting, leadership, and clinical teams to specialty meetings.",
        "Pitch curated team dinners, physician recruiting meals, and easy group reservations close to Moscone hotels.",
    ),
    "Behavioral health treatment network": (
        "Treatment networks and provider groups can use APA for referral, partnership, recruiting, and team meetings.",
        "Offer referral-partner dinners, leadership meals, and polished but practical restaurant recommendations for clinical teams.",
    ),
    "Healthtech/EHR/practice software": (
        "Software vendors run demos and buyer meetings and often need quick, reliable places for prospects and booth teams.",
        "Pitch Tabmac as an event-week dining desk for demo teams, prospect dinners, and last-minute group reservations.",
    ),
    "Neuromodulation/medical device": (
        "Device companies often host demos, clinician meetings, distributor conversations, and booth-team meals.",
        "Lead with private rooms and nearby restaurants suitable for product-demo follow-ups and clinician dinners.",
    ),
    "Clinical assessment/digital therapeutics": (
        "Assessment and digital-care vendors are likely to schedule small buyer, partner, or clinical advisor meetings.",
        "Offer small-group dinner recommendations and fast booking help for buyer follow-ups around Moscone.",
    ),
    "Research/CRO": (
        "Research organizations may meet sponsors, investigators, and clinical partners while onsite.",
        "Pitch quiet dinner spots for investigator, sponsor, and partner conversations near the convention corridor.",
    ),
    "Education/CME/publishing": (
        "Education and publishing exhibitors may need author, faculty, editor, or small customer meals.",
        "Offer casual group meal planning for authors, faculty, editorial teams, and customer meetups.",
    ),
    "Association/nonprofit": (
        "Associations may host member, board, volunteer, or small partner gatherings but budgets are often tighter.",
        "Share budget-conscious restaurant options for member meetups, staff meals, or small board dinners.",
    ),
    "Government/public-sector recruiting": (
        "Public-sector booths may have purchasing constraints, but onsite staff still need practical meal guidance.",
        "Use a low-pressure nearby dining guide for staff and candidate conversations rather than a premium event pitch.",
    ),
    "Practice services/marketing": (
        "Practice-service vendors sell to clinicians and may use dinners for prospect follow-up and partner meetings.",
        "Offer simple private-dining and restaurant shortlist support for prospect meals and vendor team dinners.",
    ),
    "Wellness/coaching": (
        "Wellness and coaching exhibitors may host informal client or community meals, usually at smaller scale.",
        "Suggest relaxed nearby restaurants for small client gatherings and team meals.",
    ),
    "Specialty/unclear exhibitor": (
        "Limited official description makes hospitality need harder to infer.",
        "Send a light-touch restaurant guide and invite them to request help for team meals or client dinners.",
    ),
}

# Map legacy 14-segment labels to Notion's 11 Industry options.
LEGACY_TO_NOTION_INDUSTRY: dict[str, NotionIndustry] = {
    "Government/public-sector recruiting": "Government / Non-profit",
    "Healthcare staffing/recruiting": "Healthcare / Pharma",
    "Neuromodulation/medical device": "Healthcare / Pharma",
    "Pharma/biotech": "Healthcare / Pharma",
    "Healthtech/EHR/practice software": "Tech / Software",
    "Clinical assessment/digital therapeutics": "Healthcare / Pharma",
    "Research/CRO": "Healthcare / Pharma",
    "Education/CME/publishing": "Education / Research",
    "Association/nonprofit": "Government / Non-profit",
    "Practice services/marketing": "Healthcare / Pharma",
    "Wellness/coaching": "Healthcare / Pharma",
    "Behavioral health treatment network": "Healthcare / Pharma",
    "Health system/provider network": "Healthcare / Pharma",
    "Specialty/unclear exhibitor": "Other",
}


def segment_for(name: str, desc: str) -> str:
    if name in NAME_SEGMENT_OVERRIDES:
        return NAME_SEGMENT_OVERRIDES[name]
    haystack = f"{name} {desc}"
    for segment, pattern in SEGMENT_RULES:
        if pattern.search(haystack):
            return segment
    return "Specialty/unclear exhibitor"


def priority_for(name: str, booth: str, desc: str, segment: str) -> NotionPriority:
    haystack = f"{name} {desc}"
    kiosk = "KIOSK" in (booth or "").upper()
    if LOW_NAME_PATTERNS.search(haystack):
        return "Low"
    if HIGH_NAME_PATTERNS.search(name):
        return "High"
    if segment == "Government/public-sector recruiting":
        return "Low"
    if segment in {"Pharma/biotech", "Healthcare staffing/recruiting"} and not kiosk:
        return "High"
    if segment in {"Health system/provider network", "Behavioral health treatment network"}:
        return "Mid"
    if segment in {"Healthtech/EHR/practice software", "Neuromodulation/medical device"}:
        return "Mid"
    if segment in {
        "Clinical assessment/digital therapeutics",
        "Research/CRO",
        "Practice services/marketing",
    }:
        return "Mid"
    if segment in {"Education/CME/publishing", "Association/nonprofit", "Wellness/coaching"}:
        return "Mid" if not kiosk else "Low"
    if kiosk or len(desc) < 80:
        return "Low"
    return "Mid"


def relevance_for(priority: NotionPriority, segment: str, booth: str) -> str:
    if priority == "High":
        return (
            f"Strong hospitality fit: {segment.lower()} exhibitor likely to have onsite "
            "team, prospect, recruiting, or partner meals."
        )
    if priority == "Mid":
        return (
            f"Moderate hospitality fit: {segment.lower()} exhibitor may need casual team "
            "meals or small-group restaurant help."
        )
    if "KIOSK" in (booth or "").upper():
        return (
            "Limited hospitality fit: kiosk presence suggests smaller onsite footprint; "
            "keep outreach lightweight."
        )
    return (
        f"Limited hospitality fit: {segment.lower()} exhibitor is less likely to buy "
        "restaurant or event support."
    )


def score_for(*, company: str, booth: str, description: str, priority: NotionPriority, segment: str) -> int:
    priority_score = {"High": 3, "Mid": 2, "Low": 1}[priority]
    segment_bonus = {
        "Pharma/biotech": 6,
        "Healthcare staffing/recruiting": 5,
        "Health system/provider network": 5,
        "Behavioral health treatment network": 5,
        "Healthtech/EHR/practice software": 4,
        "Neuromodulation/medical device": 4,
        "Practice services/marketing": 3,
        "Clinical assessment/digital therapeutics": 3,
        "Research/CRO": 3,
        "Education/CME/publishing": 2,
        "Association/nonprofit": 1,
        "Government/public-sector recruiting": 0,
        "Wellness/coaching": 0,
        "Specialty/unclear exhibitor": 0,
    }.get(segment, 0)
    booth_bonus = 2 if "," in (booth or "") else 0
    kiosk_penalty = -3 if "KIOSK" in (booth or "").upper() else 0
    desc_bonus = min(len(description) // 400, 3)
    top_bonus = 50 - TOP_TARGETS.index(company) if company in TOP_TARGETS else 0
    return top_bonus + priority_score * 10 + segment_bonus + booth_bonus + kiosk_penalty + desc_bonus


class APA26Overlay:
    """Adds APA-specific industry / priority / Tabmac notes on top of heuristic."""

    provider_id = "overlay:apa26"

    def enrich(
        self, exhibitor: RawExhibitor, profile: CompanyProfile
    ) -> dict[str, Any]:
        name = exhibitor.name
        desc = exhibitor.official_description or ""
        booth = exhibitor.booth or ""
        segment = segment_for(name, desc)
        priority = priority_for(name, booth, desc, segment)
        relevance = relevance_for(priority, segment, booth)
        why, pitch = SEGMENT_PITCH[segment]
        score = score_for(
            company=name, booth=booth, description=desc, priority=priority, segment=segment
        )

        notes_appendix = (
            f"[APA26 segment: {segment}] {why} Tabmac angle: {pitch}"
        )

        # Extras feed the CSV sink and any future overlay-aware consumers.
        extras = dict(profile.raw_exhibitor.raw_payload.get("_overlay_extras", {})) if profile.raw_exhibitor else {}
        extras.update(
            {
                "legacy_segment": segment,
                "tabmac_relevance": relevance,
                "why_contact": why,
                "suggested_pitch_angle": pitch,
            }
        )

        return {
            "industry": LEGACY_TO_NOTION_INDUSTRY.get(segment, "Other"),
            "priority": priority,
            "score": score,
            "notes_appendix": notes_appendix,
            "extras": extras,
        }
