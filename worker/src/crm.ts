// Companies CRM helpers. The CRM is a user-owned Notion database, so the worker
// only ever writes through `context.notion` and only fills columns that are
// currently empty — human edits and previously-populated curator values are
// never overwritten.

import type { CapabilityContext } from "@notionhq/workers";

import type { Company, EventSummary } from "./curator.js";
import {
	normalizeIndustryName,
	normalizePriorityName,
	normalizeWealthTierName,
} from "./normalize.js";

const INDUSTRY_COL = "Industry";
const WEALTH_TIER_COL = "Wealth Tier";
const PRIORITY_COL = "Priority";
const CONFERENCE_COL = "Conference / Trigger";

export type NotionClient = CapabilityContext["notion"];

type NotionProp = { type?: string; [k: string]: unknown };
type ExistingRow = { id: string; properties: Record<string, NotionProp> };
export type CrmSchema = { titleCol: string; knownColumns: Set<string> };

export function requireCompaniesDataSourceId(): string {
	const id = process.env.COMPANIES_DATA_SOURCE_ID;
	if (!id) {
		throw new Error("COMPANIES_DATA_SOURCE_ID env var is not set");
	}
	return id;
}

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

// Discover the CRM schema: title column name + the set of all column names.
// Querying the data source returns the schema even when it has zero rows.
export async function discoverSchema(
	notion: NotionClient,
	dataSourceId: string,
): Promise<CrmSchema> {
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

// Paginate the entire CRM once and index rows by their title text. Replaces the
// previous per-company `dataSources.query` filter, which made the tool linear in
// the company count and easily exceeded the agent's tool-call budget.
export async function loadExistingByTitle(
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

export type UpsertOutcome = "created" | "updated" | "skipped";

export async function upsertCompany(
	notion: NotionClient,
	dataSourceId: string,
	existing: ExistingRow | undefined,
	c: Company,
	event: EventSummary,
	schema: CrmSchema,
): Promise<UpsertOutcome> {
	if (existing) {
		const payload = buildEmptyFieldUpdates(existing.properties, c, event, schema.titleCol);
		if (Object.keys(payload).length === 0) return "skipped";
		await notion.pages.update({
			page_id: existing.id,
			properties: payload,
		} as never);
		return "updated";
	}
	await notion.pages.create({
		parent: { type: "data_source_id", data_source_id: dataSourceId },
		properties: buildCreateProperties(c, event, schema.titleCol, schema.knownColumns),
	} as never);
	return "created";
}
