# events-curator extension

Chrome extension that lets you:

1. **Check** whether the current tab is an event site — calls `POST /events/discover` on the curator API and reports the discovered company count (no enrichment, no DB write).
2. **Ingest** the event into the Notion Companies CRM — fires a webhook on the deployed worker, which runs the same logic as the `ingestEvent` tool (full discovery + enrichment + Notion upsert).

## Setup

```shell
cd extension
npm install
cp .env.example .env       # fill in the three values
npm run build              # produces dist/
```

Load unpacked: open `chrome://extensions`, enable Developer mode, click **Load unpacked**, point at `extension/dist`.

### Env vars

- `VITE_CURATOR_BASE_URL` — API base, e.g. `http://127.0.0.1:8000` for local dev or `https://ntn-api.filiq.ai` for the deployed instance.
- `VITE_WORKER_WEBHOOK_URL` — full webhook URL for the worker's `ingestFromExtension` capability. After `ntn workers deploy`, find this URL via `ntn workers capabilities list` (or the worker dashboard).
- `VITE_WORKER_WEBHOOK_SECRET` — must equal `EXTENSION_WEBHOOK_SECRET` in `worker/.env`. Generate with `openssl rand -hex 32`.

## Dev workflow

```shell
npm run dev                # vite + crxjs HMR
```

Then load `extension/dist` as unpacked — the dev server hot-reloads the popup on changes.

## Architecture

The extension does **not** talk to Notion directly. The worker already owns Notion-write logic (`worker/src/crm.ts`); we delegate to it via webhook so the integration token never ships in the extension bundle.

```
popup → POST /events/discover (curator API)  → count
popup → POST {VITE_WORKER_WEBHOOK_URL}        → fires worker.webhook → runIngest → Notion
```

Ingest is fire-and-forget: the popup shows "Ingestion triggered" once the webhook returns 200, and the user verifies rows in Notion. (Webhook handlers don't return data to the caller, and an ingest of 500 companies takes minutes — keeping the popup open would be fragile.)

## Risks

- **The webhook secret is baked into the extension bundle.** Anyone who unpacks the `.crx` can read it. Acceptable for personal-use; rotate by changing both env vars together.
- **`VITE_WORKER_WEBHOOK_URL` is only available after the first worker deploy.** Until then, the ingest button errors out — you can still test the check flow against the local API.
