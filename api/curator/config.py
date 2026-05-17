from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


NOTION_DATABASE_ID = "73b5f909b238838a970301065559ac4f"
NOTION_DATA_SOURCE_ID = "8605f909-b238-8317-8a64-0724bf02c7cc"

# Notion's Conference / Trigger select options (verified 2026-05-16).
NOTION_CONFERENCE_OPTIONS = {
    "JPM Healthcare",
    "RSA Conference",
    "Dreamforce",
    "GDC",
    "Moscone Convention",
    "Direct / None",
}

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "curator.db"


@dataclass
class Settings:
    db_path: Path
    anthropic_api_key: str | None
    firecrawl_api_key: str | None
    apollo_api_key: str | None
    enricher_order: list[str]
    notion_request_delay_ms: int

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            db_path=Path(os.environ.get("CURATOR_DB", str(DEFAULT_DB_PATH))),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY"),
            apollo_api_key=os.environ.get("APOLLO_API_KEY"),
            enricher_order=[
                p.strip()
                for p in os.environ.get("CURATOR_ENRICHERS", "agent_enricher").split(",")
                if p.strip()
            ],
            notion_request_delay_ms=int(os.environ.get("CURATOR_NOTION_DELAY_MS", "350")),
        )
