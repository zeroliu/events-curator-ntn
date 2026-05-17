// Shared ingest flow: POST to curator, paginate companies, upsert into the
// Notion Companies CRM. Used by both the `ingestEvent` tool (called from a
// Custom Agent) and the `ingestFromExtension` webhook (called from the
// Chrome extension). Keeping one implementation means Notion-write logic
// lives in one place — see crm.ts.

import type { CapabilityContext } from "@notionhq/workers";

import {
	discoverSchema,
	loadExistingByTitle,
	requireCompaniesDataSourceId,
	upsertCompany,
} from "./crm.js";
import {
	type Contact,
	enrichCompanyContact,
	fetchAllCompanies,
	ingestEvent,
} from "./curator.js";

export type IngestResult = {
	eventName: string;
	eventSourceUrl: string;
	companiesFound: number;
	companiesCreated: number;
	companiesUpdated: number;
	companiesSkipped: number;
};

export async function runIngest(
	url: string,
	notion: CapabilityContext["notion"],
): Promise<IngestResult> {
	const dataSourceId = requireCompaniesDataSourceId();

	const ingest = await ingestEvent(url);
	const companies = await fetchAllCompanies(ingest.event_id);

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

	const schema = await discoverSchema(notion, dataSourceId);
	const existingByTitle = await loadExistingByTitle(notion, dataSourceId, schema.titleCol);

	// Fetch contacts in parallel batches. force=false → returns the cached row
	// when the ingest-time pass populated one, otherwise drives a live lookup.
	// Failures fall back to null so a single bad enrichment doesn't abort ingest.
	const contactsByName = new Map<string, Contact | null>();
	const CONCURRENCY = 5;
	for (let i = 0; i < companies.length; i += CONCURRENCY) {
		const slice = companies.slice(i, i + CONCURRENCY);
		const results = await Promise.allSettled(
			slice.map((c) => enrichCompanyContact(ingest.event_id, c.name_normalized)),
		);
		results.forEach((r, idx) => {
			contactsByName.set(
				slice[idx].name_normalized,
				r.status === "fulfilled" ? r.value : null,
			);
		});
	}

	let created = 0;
	let updated = 0;
	let skipped = 0;
	for (const c of companies) {
		const outcome = await upsertCompany(
			notion,
			dataSourceId,
			existingByTitle.get(c.display_name),
			c,
			ingest.event,
			contactsByName.get(c.name_normalized) ?? null,
			schema,
		);
		if (outcome === "created") created++;
		else if (outcome === "updated") updated++;
		else skipped++;
	}

	return {
		eventName: ingest.event.name,
		eventSourceUrl: ingest.event.source_url,
		companiesFound: companies.length,
		companiesCreated: created,
		companiesUpdated: updated,
		companiesSkipped: skipped,
	};
}
