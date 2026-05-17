from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from curator.models import EventMeta, NotionRow


@dataclass
class SinkResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0


@runtime_checkable
class Sink(Protocol):
    sink_id: str

    def write(self, event: EventMeta, rows: list[NotionRow]) -> SinkResult: ...
