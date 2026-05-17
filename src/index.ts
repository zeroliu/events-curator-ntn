import { Worker } from "@notionhq/workers";
import { j } from "@notionhq/workers/schema-builder";

const worker = new Worker();
export default worker;

const CURATOR_BASE_URL = (process.env.CURATOR_BASE_URL ?? "").replace(/\/+$/, "");

// ---------------------------------------------------------------------------
// CRM column normalization
// ---------------------------------------------------------------------------

const INDUSTRY_OPTIONS = [
	{ name: "Tech / Software" },
	{ name: "Healthcare / Pharma" },
	{ name: "Finance / VC" },
	{ name: "Legal" },
	{ name: "Consulting" },
	{ name: "Education / Research" },
	{ name: "Hospitality / Events" },
	{ name: "Government / Non-profit" },
	{ name: "Gaming / Entertainment" },
	{ name: "Real Estate" },
	{ name: "Other" },
];

const WEALTH_TIER_OPTIONS = [
	{ name: "💎 Mega Cap" },
	{ name: "🏢 Large Enterprise" },
	{ name: "📈 Mid-Market" },
	{ name: "🚀 Funded Startup" },
	{ name: "🎓 Education / Research" },
	{ name: "🏛️ Government / Non-profit" },
	{ name: "🤝 Hospitality Partner" },
	{ name: "❓ SMB / Personal" },
];

function matchOption<T extends { name: string }>(
	value: string | null | undefined,
	options: T[],
): string | undefined {
	if (!value) return undefined;
	const v = value.trim().toLowerCase();
	if (!v) return undefined;
	const exact = options.find((o) => o.name.toLowerCase() === v);
	if (exact) return exact.name;
	const partial = options.find((o) => {
		const n = o.name.toLowerCase();
		return n.includes(v) || v.includes(n);
	});
	return partial?.name;
}

function normalizeIndustryName(v?: string | null): string | undefined {
	return matchOption(v, INDUSTRY_OPTIONS);
}

function normalizeWealthTierName(v?: string | null): string | undefined {
	if (!v) return undefined;
	const map: Record<string, string> = {
		mega_cap: "💎 Mega Cap",
		mega: "💎 Mega Cap",
		large_enterprise: "🏢 Large Enterprise",
		large: "🏢 Large Enterprise",
		mid_market: "📈 Mid-Market",
		mid: "📈 Mid-Market",
		midmarket: "📈 Mid-Market",
		funded_startup: "🚀 Funded Startup",
		startup: "🚀 Funded Startup",
		education: "🎓 Education / Research",
		research: "🎓 Education / Research",
		government: "🏛️ Government / Non-profit",
		non_profit: "🏛️ Government / Non-profit",
		nonprofit: "🏛️ Government / Non-profit",
		hospitality: "🤝 Hospitality Partner",
		hospitality_partner: "🤝 Hospitality Partner",
		smb: "❓ SMB / Personal",
		personal: "❓ SMB / Personal",
	};
	const key = v.trim().toLowerCase().replace(/[-\s]+/g, "_");
	return map[key] ?? matchOption(v, WEALTH_TIER_OPTIONS);
}

function normalizePriorityName(v?: string | null): string | undefined {
	if (!v) return undefined;
	const k = v.trim().toLowerCase();
	if (k === "high") return "High";
	if (k === "mid" || k === "medium") return "Mid";
	if (k === "low") return "Low";
	return undefined;
}

// ---------------------------------------------------------------------------
// Curator API
// ---------------------------------------------------------------------------

type EventSummary = {
	id: number;
	name: string;
	platform: string;
	platform_event_id: string;
	source_url: string;
	conference: string | null;
	venue: string | null;
	start_date: string | null;
	end_date: string | null;
	last_ingested_at: string;
	company_count: number;
};

type Company = {
	name_normalized: string;
	display_name: string;
	booth: string | null;
	official_description: string | null;
	website: string | null;
	industry: string | null;
	size_bucket: string | null;
	wealth_tier: string | null;
	priority: string | null;
	score: number | null;
	hq_city: string | null;
	hq_country: string | null;
	notes_appendix: string | null;
	extraction_confidence: string | null;
	source_url: string | null;
	updated_at: string;
};

type CompanyPage = {
	event_id: number;
	total: number;
	limit: number;
	offset: number;
	items: Company[];
};

type IngestResponse = {
	event_id: number;
	event: EventSummary;
	created: number;
	updated: number;
	skipped: number;
};

function requireCuratorBaseUrl(): string {
	if (!CURATOR_BASE_URL) {
		throw new Error("CURATOR_BASE_URL env var is not set");
	}
	return CURATOR_BASE_URL;
}

async function curatorFetch<T>(path: string, init?: RequestInit): Promise<T> {
	const base = requireCuratorBaseUrl();
	const res = await fetch(`${base}${path}`, {
		...init,
		headers: {
			"Content-Type": "application/json",
			...(init?.headers ?? {}),
		},
	});
	if (!res.ok) {
		const text = await res.text().catch(() => "");
		throw new Error(`Curator ${path} returned ${res.status}: ${text.slice(0, 500)}`);
	}
	return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Companies CRM (user-owned database)
// ---------------------------------------------------------------------------

function requireCompaniesDataSourceId(): string {
	const id = process.env.COMPANIES_DATA_SOURCE_ID;
	if (!id) {
		throw new Error("COMPANIES_DATA_SOURCE_ID env var is not set");
	}
	return id;
}

const INDUSTRY_COL = "Industry";
const WEALTH_TIER_COL = "Wealth Tier";
const PRIORITY_COL = "Priority";
const CONFERENCE_COL = "Conference / Trigger";

type NotionProp = { type?: string; [k: string]: unknown };
type NotionClient = Parameters<Parameters<typeof worker.tool>[1]["execute"]>[1]["notion"];

function isEmpty(prop: NotionProp | undefined): boolean {
	if (!prop) return false; // missing column → never write
	switch (prop.type) {
		case "title":
		case "rich_text": {
			const arr = (prop[prop.type] as Array<{ plain_text?: string }> | undefined) ?? [];
			return arr.every((t) => !t.plain_text || !t.plain_text.trim());
		}
		case "select":
			return prop.select == null;
		case "multi_select": {
			const arr = (prop.multi_select as unknown[] | undefined) ?? [];
			return arr.length === 0;
		}
		case "date":
			return prop.date == null;
		case "number":
			return prop.number == null;
		case "email":
			return prop.email == null || prop.email === "";
		case "phone_number":
			return prop.phone_number == null || prop.phone_number === "";
		case "url":
			return prop.url == null || prop.url === "";
		case "checkbox":
			return prop.checkbox !== true;
		default:
			return false;
	}
}

// Returns the curator-derived property payload for a company, keyed by column name.
function curatorMappedValues(
	c: Company,
	event: EventSummary,
	titleCol: string,
): Record<string, unknown> {
	const out: Record<string, unknown> = {
		[titleCol]: { title: [{ text: { content: c.display_name } }] },
	};
	const industry = normalizeIndustryName(c.industry);
	if (industry) out[INDUSTRY_COL] = { select: { name: industry } };
	const wealth = normalizeWealthTierName(c.wealth_tier);
	if (wealth) out[WEALTH_TIER_COL] = { select: { name: wealth } };
	const priority = normalizePriorityName(c.priority);
	if (priority) out[PRIORITY_COL] = { select: { name: priority } };
	if (event.name) out[CONFERENCE_COL] = { select: { name: event.name } };
	return out;
}

// Filters the curator-derived payload down to only the columns whose existing
// value on the page is empty. Missing columns (not in the schema) are dropped.
function buildEmptyFieldUpdates(
	existingProps: Record<string, NotionProp> | undefined,
	c: Company,
	event: EventSummary,
	titleCol: string,
): Record<string, unknown> {
	const props = existingProps ?? {};
	const candidates = curatorMappedValues(c, event, titleCol);
	const out: Record<string, unknown> = {};
	for (const [col, value] of Object.entries(candidates)) {
		const existing = props[col];
		if (!existing) continue;
		if (!isEmpty(existing)) continue;
		out[col] = value;
	}
	return out;
}

type ExistingRow = { id: string; properties: Record<string, NotionProp> };

// Paginate the entire CRM once and index rows by their title text. Replaces the
// previous per-company `dataSources.query` filter, which made the tool linear in
// the company count and easily exceeded the agent's tool-call budget.
async function loadExistingByTitle(
	notion: NotionClient,
	dataSourceId: string,
	titleCol: string,
): Promise<Map<string, ExistingRow>> {
	const byTitle = new Map<string, ExistingRow>();
	let startCursor: string | undefined;
	while (true) {
		const res = (await notion.dataSources.query({
			data_source_id: dataSourceId,
			page_size: 100,
			start_cursor: startCursor,
		} as never)) as {
			results: Array<{ id: string; properties?: Record<string, NotionProp> }>;
			next_cursor: string | null;
			has_more: boolean;
		};
		for (const row of res.results) {
			const props = row.properties ?? {};
			const titleProp = props[titleCol];
			const arr =
				(titleProp?.title as Array<{ plain_text?: string }> | undefined) ?? [];
			const title = arr.map((t) => t.plain_text ?? "").join("");
			if (!title) continue;
			// Preserve first-wins to match the old `page_size: 1` behavior on duplicates.
			if (!byTitle.has(title)) byTitle.set(title, { id: row.id, properties: props });
		}
		if (!res.has_more || !res.next_cursor) break;
		startCursor = res.next_cursor;
	}
	return byTitle;
}

// Discover the CRM schema: title column name + the set of all column names.
// Querying the data source returns the schema even when it has zero rows.
async function discoverSchema(
	notion: NotionClient,
	dataSourceId: string,
): Promise<{ titleCol: string; knownColumns: Set<string> }> {
	const ds = (await notion.dataSources.retrieve({
		data_source_id: dataSourceId,
	} as never)) as {
		properties?: Record<string, { type?: string }>;
	};
	const props = ds.properties ?? {};
	const titleCol = Object.entries(props).find(([, p]) => p.type === "title")?.[0];
	if (!titleCol) {
		throw new Error(
			`Companies CRM data source ${dataSourceId} has no title property — cannot look up rows.`,
		);
	}
	return { titleCol, knownColumns: new Set(Object.keys(props)) };
}

function buildCreateProperties(
	c: Company,
	event: EventSummary,
	titleCol: string,
	knownColumns: Set<string>,
): Record<string, unknown> {
	const values = curatorMappedValues(c, event, titleCol);
	const out: Record<string, unknown> = {};
	for (const [col, value] of Object.entries(values)) {
		if (knownColumns.has(col)) out[col] = value;
	}
	return out;
}

// ---------------------------------------------------------------------------
// Tool: ingestEvent
// ---------------------------------------------------------------------------

worker.tool("ingestEvent", {
	title: "Ingest Event",
	description:
		"Scrape an event page and populate the Companies CRM with the companies attending. " +
		"Existing CRM rows are preserved — only empty fields are filled, so human edits stay intact.",
	schema: j.object({
		url: j.string().describe("The source URL for the event (e.g. the conference website)."),
	}),
	execute: async ({ url }, { notion }) => {
		const dataSourceId = requireCompaniesDataSourceId();

		const ingest = await curatorFetch<IngestResponse>("/events/ingest", {
			method: "POST",
			body: JSON.stringify({ url }),
		});

		const companies: Company[] = [];
		let offset = 0;
		while (true) {
			const page = await curatorFetch<CompanyPage>(
				`/events/${ingest.event_id}/companies?limit=200&offset=${offset}`,
			);
			companies.push(...page.items);
			offset += page.items.length;
			if (page.items.length === 0 || offset >= page.total) break;
		}

		if (companies.length === 0) {
			return {
				eventName: ingest.event.name,
				eventSourceUrl: ingest.event.source_url,
				companiesFound: 0,
				companiesCreated: 0,
				companiesUpdated: 0,
				companiesSkipped: 0,
			};
		}

		const { titleCol, knownColumns } = await discoverSchema(notion, dataSourceId);
		const existingByTitle = await loadExistingByTitle(notion, dataSourceId, titleCol);

		let created = 0;
		let updated = 0;
		let skipped = 0;
		for (const c of companies) {
			const existing = existingByTitle.get(c.display_name);
			if (existing) {
				const payload = buildEmptyFieldUpdates(
					existing.properties,
					c,
					ingest.event,
					titleCol,
				);
				if (Object.keys(payload).length > 0) {
					await notion.pages.update({
						page_id: existing.id,
						properties: payload,
					} as never);
					updated++;
				} else {
					skipped++;
				}
			} else {
				await notion.pages.create({
					parent: { type: "data_source_id", data_source_id: dataSourceId },
					properties: buildCreateProperties(c, ingest.event, titleCol, knownColumns),
				} as never);
				created++;
			}
		}

		return {
			eventName: ingest.event.name,
			eventSourceUrl: ingest.event.source_url,
			companiesFound: companies.length,
			companiesCreated: created,
			companiesUpdated: updated,
			companiesSkipped: skipped,
		};
	},
});
