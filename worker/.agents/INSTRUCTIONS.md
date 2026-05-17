# Repository Guidelines

## This worker: events-curator-ntn

**Architecture (one tool, no syncs, no managed databases):**

- A Notion Custom Agent calls the `ingestEvent` tool with a URL.
- The tool POSTs to the events-curator API (`CURATOR_BASE_URL`) at `/events/ingest`, then paginates `/events/{event_id}/companies`.
- For each company returned by the curator, the tool upserts a row in the **user-owned** Companies CRM via `context.notion`:
  - Lookup by the database's **title column** (whatever it's named) with `title.equals = company.display_name`.
  - If no match → create a new row with all curator-mapped properties.
  - If match → only fill columns whose current value is empty. Human edits and previously-populated curator values are never overwritten.
  - Caveat: lookup is case-sensitive and exact, so renaming a title in Notion ("Acme" → "Acme Corp.") will cause the next ingest to create a duplicate. Merge by hand if it happens.
- The Companies CRM is **not** declared with `worker.database()` — it's a regular Notion database the user maintains, so it stays human-writeable. We discover the data-source-id from `process.env.COMPANIES_DATA_SOURCE_ID`.
- There is no Events database. Each company row tags its source event via a `Conference / Trigger` single-select (option = curator's `event.name`; Notion auto-creates new options as needed).

**CRM schema** (column names must match exactly; missing columns are silently skipped — the tool never errors on a missing column):

| Property | Type | Source |
| --- | --- | --- |
| _your title column_ | title | curator `display_name` — name doesn't matter, the tool auto-detects it via `dataSources.retrieve` |
| Industry | select | normalized curator industry |
| Wealth Tier | select | normalized curator wealth_tier |
| Priority | select | normalized curator priority |
| Conference / Trigger | select | curator `event.name` |
| Est. GMV | number | curator `gmv_usd` |

All other CRM columns (Contact Name, Email, Notes, etc.) are human-only and never touched by the tool.

**Environment variables (`.env`):**

- `NOTION_API_TOKEN` — internal integration; the integration must be shared with the Companies CRM in Notion.
- `CURATOR_BASE_URL` — base URL of the events-curator API (no trailing slash).
- `COMPANIES_DATA_SOURCE_ID` — obtain via `ntn datasources resolve <crm-database-id>` once after sharing the CRM with the integration.

**Operating the worker:**

```shell
npm run check                          # type-check
ntn workers deploy                     # deploy the tool
ntn workers exec ingestEvent --local -d '{"url":"https://..."}'   # run locally against .env
ntn workers exec ingestEvent -d '{"url":"https://..."}'           # run on the deployed worker
ntn workers capabilities list          # should show only `ingestEvent` + `curatorApi`
```

## Project Structure & Module Organization
- `src/index.ts` defines the worker. Single tool (`ingestEvent`) and a curator pacer; no databases, syncs, or webhooks.
- Generated: `dist/` build output, `workers.json` CLI config.

## Worker & Capability API (SDK)

`@notionhq/workers` provides `Worker`, schema helpers, and builders; the `ntn` CLI powers worker management. This worker only uses `worker.tool()` and `worker.pacer()`. If you ever need other capabilities (syncs, webhooks, OAuth), consult the upstream docs — they're intentionally not duplicated here.

```ts
import { Worker } from "@notionhq/workers";

const worker = new Worker();
export default worker;

// Rate-limit calls to an external service.
const myApi = worker.pacer("myApi", { allowedRequests: 10, intervalMs: 1000 });

worker.tool("sayHello", {
	title: "Say Hello",
	description: "Return a greeting",
	schema: { type: "object", properties: { name: { type: "string" } }, required: ["name"], additionalProperties: false },
	execute: async ({ name }, { notion }) => {
		await myApi.wait();
		return `Hello, ${name}`;
	},
});
```

### Notion API access (`context.notion`)

Every `execute` handler receives `context.notion` (a `@notionhq/client` SDK instance). For **tool** capabilities invoked by a Custom Agent — the case for this worker — the platform sets `NOTION_API_TOKEN` automatically using the agent's permissions, so `context.notion` is pre-authenticated.

When running locally via `ntn workers exec ingestEvent --local`, the `NOTION_API_TOKEN` from `worker/.env` is used instead (must be an internal integration shared with the Companies CRM).

### Pacers (rate limiting)

The worker declares one pacer:

```ts
const curatorApi = worker.pacer("curatorApi", { allowedRequests: 10, intervalMs: 1000 });
```

Call `await curatorApi.wait()` before every HTTP request to the events-curator API inside `execute`. Notion API calls go through `context.notion` and don't need pacing.

### Querying a database (one-time setup helper)

To get `COMPANIES_DATA_SOURCE_ID` from a Notion database URL, use the `ntn` CLI:

```shell
ntn datasources resolve <database-id>   # database URL → data source ID(s)
ntn datasources query <data-source-id>  # sanity-check the rows
```

A Notion database is a container for one or more data sources; the public API queries data sources directly. If `query` returns 404, the ID is a database ID — `resolve` it first.

## Build, Test, and Development Commands
- Node >= 22 and npm >= 10.9.2 (see `package.json` engines).
- `npm run build` — compile TypeScript to `dist/`.
- `npm run check` — type-check only (no emit).
- `ntn login` — connect to a Notion workspace.
- `ntn workers deploy` — build and publish the worker.
- `ntn workers exec ingestEvent [--local]` — run the tool.
- `ntn workers env push` — push secrets to the deployed worker (skip for `--local`).

## Debugging & Monitoring Runs

```shell
ntn workers runs list                                                    # recent runs
ntn workers runs logs <runId>                                            # logs for one run
ntn workers runs list --plain | head -n1 | cut -f1 | xargs -I{} ntn workers runs logs {}   # latest run, any capability
ntn workers runs list --plain | grep ingestEvent | head -n1 | cut -f1 | xargs -I{} ntn workers runs logs {}   # latest ingestEvent run
```

`--plain` outputs tab-separated values, easy to pipe.

## Coding Style & Naming Conventions
- TypeScript with `strict` enabled; keep types explicit when shaping I/O.
- Use tabs for indentation; capability keys in lowerCamelCase.

## Testing Guidelines
- No test runner configured. Validate with `npm run check` for types and `./test.sh` for end-to-end.
- `test.sh` invokes `ntn workers exec ingestEvent --local` against the URL passed via `URL=...` (defaults to `https://example-event.com`).
- `--local` runs against `worker/.env`; the deployed variant requires `ntn workers env push` first.

## Commit & Pull Request Guidelines
- Messages typically use `feat(scope): ...`, `TASK-123: ...`, or version bumps.
- PRs should describe changes and list the commands you ran to verify.
