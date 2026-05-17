import type { Worker } from "@notionhq/workers";
import { j } from "@notionhq/workers/schema-builder";

import { runIngest } from "../ingest-flow.js";

export function registerIngestEvent(worker: Worker): void {
	worker.tool("ingestEvent", {
		title: "Show Me Math",
		description:
			"Scrape an event page and populate the Companies CRM with the companies attending. " +
			"Existing CRM rows are preserved — only empty fields are filled, so human edits stay intact.",
		schema: j.object({
			url: j.string().describe("The source URL for the event (e.g. the conference website)."),
		}),
		execute: async ({ url }, { notion }) => {
			return runIngest(url, notion);
		},
	});
}
