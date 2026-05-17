from __future__ import annotations

import json
import sys

from curator.models import EventMeta, NotionRow
from curator.sinks.base import SinkResult


class StdoutSink:
    sink_id = "stdout"

    def write(self, event: EventMeta, rows: list[NotionRow]) -> SinkResult:
        for row in rows:
            payload = {
                "company": row.company.display_name,
                "industry": row.company.industry,
                "wealth_tier": row.company.wealth_tier,
                "priority": row.company.priority,
                "score": row.company.score,
                "legacy_segment": row.company.extras.get("legacy_segment"),
                "conference": row.conference,
                "event_date": row.event_date.isoformat() if row.event_date else None,
            }
            print(json.dumps(payload, ensure_ascii=False))
        print(
            f"# {event.name} | platform={event.platform} | rows={len(rows)}",
            file=sys.stderr,
        )
        return SinkResult(created=len(rows))
