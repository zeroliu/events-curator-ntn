#!/usr/bin/env bash
set -euo pipefail

# Local test harness for the events-curator-ntn worker.
#
# Prereqs:
#   1. .env is filled in:
#        - NOTION_API_TOKEN (integration with access to the Companies CRM)
#        - CURATOR_BASE_URL (running curator)
#        - COMPANIES_DATA_SOURCE_ID (from `ntn datasources resolve <db-id>`)
#   2. Companies CRM exists in Notion with the required columns
#      (see CLAUDE.md → "Required CRM schema").
#
# Override the URL via env var:
#   URL=https://example-event.com ./test.sh

URL="${URL:-https://example-event.com}"

echo "==> Tool: ingestEvent (url=$URL)"
ntn workers exec ingestEvent --local -d "{\"url\":\"$URL\"}"
