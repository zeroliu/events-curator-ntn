import type { Worker } from "@notionhq/workers";
import { j } from "@notionhq/workers/schema-builder";

import {
	discoverSchema,
	loadExistingByTitle,
	requireCompaniesDataSourceId,
	upsertCompany,
} from "../crm.js";
import { fetchAllCompanies, ingestEvent } from "../curator.js";

export function registerIngestEvent(worker: Worker): void {
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
		},
	});
}
