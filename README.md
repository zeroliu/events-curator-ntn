# events-curator-ntn

Monorepo for the Moscone events-curator stack.

| Folder | Project | Stack |
| --- | --- | --- |
| [`worker/`](./worker) | Notion ntn worker — exposes the `ingestEvent` tool that a Notion Custom Agent calls to populate the Companies CRM. | Node 22+, TypeScript, `@notionhq/workers` |
| [`api/`](./api) | events-curator HTTP service — runs the discovery + enrichment pipeline against an event URL and exposes results the worker reads. | Python 3.11+, FastAPI, SQLite |

The worker calls the API at `CURATOR_BASE_URL`. The two ship independently.

## Quick start

```shell
# 1. start the API (terminal 1)
cd api
pip install -e .
uvicorn curator.api.main:app --reload

# 2. point the worker at it (terminal 2)
cd worker
npm install
# set CURATOR_BASE_URL=http://localhost:8000 in worker/.env
./test.sh URL=https://example-event.com
```

See [`worker/CLAUDE.md`](./worker/CLAUDE.md) and [`api/CLAUDE.md`](./api/CLAUDE.md) for project-specific details.
