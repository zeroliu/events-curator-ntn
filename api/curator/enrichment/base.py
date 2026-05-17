from __future__ import annotations

from typing import Protocol, runtime_checkable

from curator.models import CompanyProfile, RawExhibitor


@runtime_checkable
class CompanyEnricher(Protocol):
    """Reads a raw exhibitor + the in-flight profile and returns updates.

    Returning ``{}`` (or no keys) means "no opinion". The pipeline merges
    non-null fields and records provenance in ``CompanyProfile.enrichment_sources``.
    """

    provider_id: str

    def enrich(
        self, exhibitor: RawExhibitor, profile: CompanyProfile
    ) -> dict[str, object]: ...
