# events-curator API

FastAPI + SQLite service that runs the discovery + enrichment pipeline against an event URL and exposes the results as JSON. Consumed by the sibling `worker/` ntn worker via `CURATOR_BASE_URL`.

## Layout

```
curator/
├── api/          # FastAPI app (main.py, schemas.py, service.py)
├── cli.py        # `curator` console script — manual pipeline runs
├── config.py     # Settings.load() reads env vars
├── pipeline.py   # discovery → enrichment → sink orchestration
├── discovery/    # source-specific scrapers (mapyourshow, rainfocus, firecrawl_llm) + resolver
├── enrichment/   # heuristic + website_llm enrichers, with per-event overlays
├── people_enrichment/   # Apollo + LLM contact lookup
├── sinks/        # csv / sqlite / stdout output sinks
└── storage/      # SQLite schema + repo functions used by the API
```

## Running

```shell
# install (uses pyproject.toml; egg-info regenerates)
pip install -e .

# run the API
uvicorn curator.api.main:app --reload   # http://localhost:8000/docs

# run the CLI directly (no API)
curator <event-url>
```

The worker hits `POST /events/ingest` then paginates `GET /events/{event_id}/companies` — keep those response shapes stable (see `api/schemas.py`). `POST /events/ingest` now also runs people enrichment best-effort (parallel, capped at 5 concurrent; cached globally by `name_normalized`), so `GET /events/{event_id}/companies/{name_normalized}/contact` typically returns `status: "enriched"` straight after ingest with no extra round trip. `POST /events/{event_id}/companies/{name_normalized}/contact/enrich` remains as a fallback/retry path for companies the ingest-time pass skipped or failed on (pass `{"force": true}` to bypass cache). Other GET endpoints (`/events`, `/events/{id}`, `/health`) are diagnostic.

## Environment (`.env`, see `.env.example`)

- `FIRECRAWL_API_KEY` — required for the LLM-backed discovery path.
- `ANTHROPIC_API_KEY` — required for `website_llm` enrichment and people enrichment LLM calls.
- `APOLLO_API_KEY` — required for `people_enrichment.apollo`.
- `CURATOR_ENRICHERS` — comma-separated enricher order. Default `agent_enricher` (requires the Claude Code CLI to be installed and logged in — see `claude_agent_sdk`). Other choices: `heuristic`, `website_llm`, `apollo`.
- `CURATOR_DB` — sqlite path (default `api/data/curator.db`).
- `CURATOR_NOTION_DELAY_MS` — pacing for the Notion-facing select option list (default 350).

To wipe enrichment caches (e.g. after changing the prompt or schema):

```shell
sqlite3 api/data/curator.db "DELETE FROM enrichment_cache;"
```

## Contract with the worker

The worker assumes the title column of the Notion CRM maps to `Company.display_name`, and reads these select-friendly fields per company: `industry`, `wealth_tier`, `priority`, plus `event.name`. If you add fields the worker should pick up, update `worker/src/index.ts` in the same change.

## Notes

- `data/` holds the runtime sqlite db — gitignored.
- `curator/mapping/` was removed; the legacy `outputs/` CSV samples were removed too (`api/sinks/csv_sink.py` still writes CSVs to wherever you point it).
- The `curator` package name and the CLI script (`curator = curator.cli:main`) come from `pyproject.toml`.
