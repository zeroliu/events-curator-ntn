// HTTP client for the events-curator API. The worker only talks to two endpoints:
// POST /events/ingest (kicks off discovery) and GET /events/{id}/companies
// (paginated results).

const CURATOR_BASE_URL = (process.env.CURATOR_BASE_URL ?? "").replace(/\/+$/, "");

export type EventSummary = {
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

export type Company = {
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
	gmv_usd: number | null;
	gmv_confidence: "high" | "medium" | "low" | null;
	gmv_note: string | null;
	updated_at: string;
};

type CompanyPage = {
	event_id: number;
	total: number;
	limit: number;
	offset: number;
	items: Company[];
};

export type IngestResponse = {
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

export function ingestEvent(url: string): Promise<IngestResponse> {
	return curatorFetch<IngestResponse>("/events/ingest", {
		method: "POST",
		body: JSON.stringify({ url }),
	});
}

export async function fetchAllCompanies(eventId: number): Promise<Company[]> {
	const companies: Company[] = [];
	let offset = 0;
	while (true) {
		const page = await curatorFetch<CompanyPage>(
			`/events/${eventId}/companies?limit=200&offset=${offset}`,
		);
		companies.push(...page.items);
		offset += page.items.length;
		if (page.items.length === 0 || offset >= page.total) break;
	}
	return companies;
}
