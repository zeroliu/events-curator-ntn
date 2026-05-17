from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from curator.models import EventHints, EventMeta, RawExhibitor

_SUBDOMAIN_RE = re.compile(r"^https?://([a-z0-9-]+)\.mapyourshow\.com", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_PAGE_SIZE = 500
_USER_AGENT = "events-curator/0.1 (+https://github.com/tabmac)"


def _clean(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", value or "").strip()


def _extract_slug(url: str) -> str | None:
    match = _SUBDOMAIN_RE.match(url)
    return match.group(1).lower() if match else None


class MapYourShowAdapter:
    platform_id = "mapyourshow"

    def matches(self, url: str) -> bool:
        return _extract_slug(url) is not None

    def fetch(
        self, url: str, hints: EventHints, *, force_refresh: bool = False
    ) -> tuple[EventMeta, list[RawExhibitor]]:
        slug = _extract_slug(url)
        if slug is None:
            raise ValueError(f"not a MapYourShow URL: {url}")

        base = f"https://{slug}.mapyourshow.com"
        endpoint = f"{base}/8_0/ajax/remote-proxy.cfm"

        client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{base}/8_0/",
                "X-Requested-With": "XMLHttpRequest",
            },
            follow_redirects=True,
        )
        try:
            exhibitors: list[RawExhibitor] = []
            start = 0
            total_hits = None
            while True:
                params = {
                    "action": "search",
                    "searchtype": "exhibitorgallery",
                    "searchsize": _PAGE_SIZE,
                    "start": start,
                }
                response = client.get(endpoint, params=params)
                response.raise_for_status()
                payload = response.json()
                results = (
                    payload.get("DATA", {})
                    .get("results", {})
                    .get("exhibitor", {})
                )
                hits = results.get("hit", [])
                total_hits = results.get("found", payload.get("DATA", {}).get("totalhits", len(hits)))

                for hit in hits:
                    exhibitor = _hit_to_exhibitor(hit, base)
                    if exhibitor is not None:
                        exhibitors.append(exhibitor)

                start += len(hits)
                if not hits or start >= int(total_hits or 0):
                    break

            event_name = hints.event_name or _derive_event_name(slug)
            meta = EventMeta(
                name=event_name,
                platform=self.platform_id,
                platform_event_id=slug,
                source_url=url,
                venue=hints.venue,
                start_date=hints.event_date,
                end_date=hints.event_date,
            )
            return meta, exhibitors
        finally:
            client.close()


def _hit_to_exhibitor(hit: dict[str, Any], base: str) -> RawExhibitor | None:
    fields = hit.get("fields", {})
    name = _clean(fields.get("exhname_t"))
    if not name:
        return None

    booths = fields.get("boothsdisplay_la", [])
    if isinstance(booths, str):
        booths = [booths]
    booth = ", ".join(b.replace("randomstring", "") for b in booths if b)

    desc = _clean(fields.get("exhdesc_t"))

    # Website fields vary across MYS deployments.
    website = None
    for key in ("exhweburl_t", "exhwebsite_t", "exhibitorwebsite_t", "website_t"):
        candidate = fields.get(key)
        if candidate:
            website = _clean(candidate)
            break

    source_url = None
    exhid = fields.get("exhid_l") or fields.get("exhid_s") or fields.get("exhid_t")
    if exhid:
        source_url = f"{base}/8_0/exhibitor/exhibitor-details.cfm?exhid={exhid}"

    return RawExhibitor(
        name=name,
        booth=booth or None,
        official_description=desc or None,
        website=website,
        source_url=source_url,
        raw_payload=fields,
    )


def _derive_event_name(slug: str) -> str:
    # `apa26` -> "APA 26", `hlth25` -> "HLTH 25". Best effort, user can override.
    match = re.match(r"^([a-z]+)(\d+)$", slug)
    if match:
        return f"{match.group(1).upper()} {match.group(2)}"
    return slug.upper()
