CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    platform_event_id TEXT NOT NULL,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    conference TEXT,
    venue TEXT,
    start_date TEXT,
    end_date TEXT,
    last_ingested_at TEXT NOT NULL,
    UNIQUE (platform, platform_event_id)
);

CREATE TABLE IF NOT EXISTS event_companies (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name_normalized TEXT NOT NULL,
    display_name TEXT NOT NULL,
    booth TEXT,
    official_description TEXT,
    website TEXT,
    industry TEXT,
    size_bucket TEXT,
    wealth_tier TEXT,
    priority TEXT,
    score INTEGER,
    hq_city TEXT,
    hq_country TEXT,
    notes_appendix TEXT,
    extraction_confidence TEXT,
    extras_json TEXT,
    enrichment_sources_json TEXT,
    raw_payload_json TEXT,
    source_url TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (event_id, name_normalized)
);

CREATE INDEX IF NOT EXISTS idx_event_companies_event ON event_companies(event_id);
CREATE INDEX IF NOT EXISTS idx_event_companies_priority ON event_companies(priority);
CREATE INDEX IF NOT EXISTS idx_event_companies_industry ON event_companies(industry);

CREATE TABLE IF NOT EXISTS enrichment_cache (
    provider TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (provider, cache_key)
);

CREATE TABLE IF NOT EXISTS notion_id_by_company (
    name_normalized TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    last_synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL,
    platform TEXT NOT NULL,
    conference TEXT,
    exhibitor_count INTEGER NOT NULL,
    created_count INTEGER NOT NULL,
    updated_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_company_contacts (
    event_id INTEGER NOT NULL,
    name_normalized TEXT NOT NULL,
    person_name TEXT,
    title TEXT,
    email TEXT,
    phone TEXT,
    sources_json TEXT,
    confidence TEXT NOT NULL,
    reasoning TEXT,
    provider TEXT,
    enriched_at TEXT NOT NULL,
    PRIMARY KEY (event_id, name_normalized),
    FOREIGN KEY (event_id, name_normalized)
        REFERENCES event_companies(event_id, name_normalized) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_event_company_contacts_event ON event_company_contacts(event_id);
