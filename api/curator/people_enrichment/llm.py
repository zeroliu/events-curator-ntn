"""Claude Agent SDK fallback: uses the locally-installed Claude Code CLI's
credentials (Keychain / ~/.claude/.credentials.json / CLAUDE_CODE_OAUTH_TOKEN).
No API key is read or passed from this codebase."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from curator.people_enrichment.models import ResearchResult
from curator.people_enrichment.prompts import build_research_prompt

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Mirror the camelCase keys from the prompt's required output shape.
RESEARCH_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "personName": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "email": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
        "sources": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["personName", "title", "email", "phone", "sources", "confidence", "reasoning"],
}


async def claude_research(company_name: str) -> ResearchResult:
    """Run Claude with WebSearch + JSON-schema output. Raises on SDK failure
    (e.g. CLI missing or unauthenticated) so the caller can surface 503."""
    options = ClaudeAgentOptions(
        allowed_tools=["WebSearch"],
        max_turns=8,
        output_format={"type": "json_schema", "schema": RESEARCH_RESULT_SCHEMA},
    )

    structured: dict[str, Any] | None = None
    last_text: str = ""

    async for msg in query(prompt=build_research_prompt(company_name), options=options):
        if isinstance(msg, ResultMessage):
            structured = getattr(msg, "structured_output", None)
            break
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    last_text = block.text

    payload = structured if structured is not None else _extract_json_object(last_text)
    if payload is None:
        log.error("[claude] no parseable JSON in response for %r. raw=%r", company_name, last_text)
        return ResearchResult(
            confidence="low",
            reasoning=f"No parseable JSON in LLM response for {company_name}.",
            provider="claude",
        )

    return _build_result(payload)


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


def _build_result(parsed: dict[str, Any]) -> ResearchResult:
    email = parsed.get("email")
    if isinstance(email, str):
        email = email.strip()
        email = email if EMAIL_RE.match(email) else None
    else:
        email = None

    sources_raw = parsed.get("sources") or []
    sources = [s for s in sources_raw if isinstance(s, str)]
    confidence = parsed.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    return ResearchResult(
        person_name=_str_or_none(parsed.get("personName")),
        title=_str_or_none(parsed.get("title")),
        email=email,
        phone=_str_or_none(parsed.get("phone")),
        sources=sources,
        confidence=confidence,
        reasoning=parsed.get("reasoning") if isinstance(parsed.get("reasoning"), str) else "",
        provider="claude",
    )


def _str_or_none(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s or None
