# events-curator-ntn

Monorepo for two coupled projects:

- **`worker/`** — Notion ntn worker (Node/TypeScript). Exposes the `ingestEvent` tool that a Notion Custom Agent calls to populate the Companies CRM.
- **`api/`** — events-curator HTTP service (Python / FastAPI). Runs the discovery + enrichment pipeline against an event URL and exposes the results the worker reads.

The worker calls the API at `CURATOR_BASE_URL`. They ship and run independently.

## Working in this repo

- `cd worker/` for any `npm` or `ntn workers …` command. See `worker/CLAUDE.md` for worker-specific architecture, env vars, CRM schema, and the full Notion Workers SDK reference.
- `cd api/` for any `uvicorn`, `python`, or `curator` CLI command. See `api/CLAUDE.md` for the API layout, run instructions, and the contract the worker depends on.

Per-project `CLAUDE.md` files are the source of truth — Claude Code auto-loads the nearest one based on `cwd`.
