# events-curator-ntn worker

Notion ntn worker that exposes the `ingestEvent` tool to a Notion Custom Agent. Given an event URL, it calls the sibling [events-curator API](../api) and upserts the returned companies into a user-owned **Companies CRM** in Notion.

## Run

```shell
npm install
cp .env.example .env   # fill in NOTION_API_TOKEN, CURATOR_BASE_URL, COMPANIES_DATA_SOURCE_ID
ntn login              # connect to a Notion workspace
ntn workers exec ingestEvent --local -d '{"url":"https://..."}'   # run locally against .env
./test.sh URL=https://...                                          # same, via the test script
```

Deploy:

```shell
npm run check                  # type-check
ntn workers env push           # push .env to the deployed worker
ntn workers deploy             # build + publish
ntn workers exec ingestEvent -d '{"url":"https://..."}'   # run on the deployed worker
```

## How it works

- The tool POSTs to `CURATOR_BASE_URL/events/ingest`, then paginates `/events/{event_id}/companies`.
- For each company, it upserts a row in the Companies CRM (discovered via `COMPANIES_DATA_SOURCE_ID`):
  - Lookup is by the database's **title column** with `title.equals = company.display_name`.
  - New company → create row with curator-mapped properties.
  - Existing company → fill only empty columns. Human edits and prior curator values are never overwritten.
- The CRM is a regular user-maintained Notion database (not declared with `worker.database()`), so it stays human-writeable.

Mapped columns (missing columns are silently skipped):

| Property | Type | Source |
| --- | --- | --- |
| _title column_ | title | curator `display_name` (auto-detected name) |
| Industry | select | normalized curator industry |
| Wealth Tier | select | normalized curator wealth_tier |
| Priority | select | normalized curator priority |
| Conference / Trigger | select | curator `event.name` |

See [`CLAUDE.md`](./CLAUDE.md) for the full Notion Workers SDK reference, debugging commands, and the contract this worker depends on.
