from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]
Provider = Literal["apollo", "anthropic"]


class ResearchResult(BaseModel):
    """One person's contact details, the unit returned by every provider."""

    person_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    sources: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"
    reasoning: str = ""
    provider: Provider | None = None
