from __future__ import annotations

import re

from curator.models import EventHints, EventMeta, RawExhibitor

# Known mapping from public event sites to their RainFocus registration hosts.
# Populated as we onboard each event.
KNOWN_EVENTS: dict[str, str] = {
    # "dreamforce.com": "reg.salesforce.com/flow/plat/df26/...",
}

_REG_FLOW_RE = re.compile(
    r"^https?://reg\.[a-z0-9-]+\.com/flow/[^/]+/[^/]+/", re.IGNORECASE
)


def looks_like_rainfocus(url: str) -> bool:
    """URL-shape check used by the resolver to flag RainFocus catalogs.

    Decoupled from `RainFocusAdapter.matches()` because the adapter is gated
    off until extraction is implemented — but the resolver still wants to
    recognize the platform so it doesn't waste a Firecrawl call resolving a
    URL that already points at a catalog.
    """
    if _REG_FLOW_RE.match(url):
        return True
    return any(host in url for host in KNOWN_EVENTS)


class RainFocusAdapter:
    """RainFocus catalog adapter.

    Status: gated. The catalog JSON API is event-specific and must be
    reverse-engineered against a live show before this can be implemented.
    `matches()` returns False so the registry falls through to
    `firecrawl_llm` — once `fetch()` is real, flip `_READY = True`.
    """

    platform_id = "rainfocus"
    _READY = False

    def matches(self, url: str) -> bool:
        if not self._READY:
            return False
        return looks_like_rainfocus(url)

    def fetch(
        self, url: str, hints: EventHints, *, force_refresh: bool = False
    ) -> tuple[EventMeta, list[RawExhibitor]]:
        raise NotImplementedError(
            "RainFocus adapter not implemented yet. "
            "Use --adapter firecrawl_llm or implement curator/discovery/rainfocus.py:fetch."
        )
