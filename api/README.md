# events-curator API

FastAPI service that ingests an event URL, runs discovery + enrichment, and exposes the resulting company list as JSON for the sibling [ntn worker](../worker).

## Run

```shell
pip install -e .
cp .env.example .env   # fill in FIRECRAWL_API_KEY, ANTHROPIC_API_KEY, APOLLO_API_KEY
uvicorn curator.api.main:app --reload
open http://localhost:8000/docs
```

CLI (skip the API and run the pipeline directly):

```shell
curator <event-url>
```

## Key endpoints

- `POST /events/ingest` — body `{ "url": "..." }` → runs the discovery + company-enrichment pipeline, returns `event_id`.
- `GET /events/{event_id}/companies` — paginated company list the worker consumes (filter by `industry`, `priority`, `wealth_tier`).
- `GET /events/{event_id}/companies/{name_normalized}/contact` — cache read for a company's contact. Returns `status: "enriched"` with person details, or `status: "not_enriched"` with null fields. 404 only if event/company doesn't exist.
- `POST /events/{event_id}/companies/{name_normalized}/contact/enrich` — runs the people-enrichment pipeline (Apollo → Claude Agent SDK fallback). Returns the cached contact on hit; pass body `{"force": true}` to bypass cache and re-run.
- `GET /events`, `GET /events/{event_id}`, `GET /health` — diagnostic.

See [`CLAUDE.md`](./CLAUDE.md) for package layout, env vars, and the contract the worker depends on.
