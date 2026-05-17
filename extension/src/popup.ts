import { discover, getActiveTabUrl, triggerIngest } from "./api";
import type { DiscoverSuccess } from "./types";

type State =
	| { kind: "idle" }
	| { kind: "checking" }
	| { kind: "no_match"; reason?: string }
	| { kind: "found"; data: DiscoverSuccess }
	| { kind: "ingesting"; data: DiscoverSuccess }
	| { kind: "ingest_done"; data: DiscoverSuccess }
	| { kind: "error"; message: string };

const urlEl = document.getElementById("current-url") as HTMLDivElement;
const statusEl = document.getElementById("status") as HTMLElement;
const checkBtn = document.getElementById("check-btn") as HTMLButtonElement;
const ingestBtn = document.getElementById("ingest-btn") as HTMLButtonElement;

let currentUrl: string | null = null;
let state: State = { kind: "idle" };

async function init(): Promise<void> {
	currentUrl = await getActiveTabUrl();
	urlEl.textContent = currentUrl ?? "(no http(s) URL — open a real web page)";
	if (!currentUrl) {
		checkBtn.disabled = true;
	}
	render();
}

function render(): void {
	statusEl.className = "";
	statusEl.innerHTML = "";
	ingestBtn.hidden = true;
	ingestBtn.disabled = false;
	checkBtn.disabled = !currentUrl;
	checkBtn.textContent = "Check";

	switch (state.kind) {
		case "idle":
			break;
		case "checking":
			checkBtn.disabled = true;
			checkBtn.innerHTML = '<span class="spinner"></span>Checking…';
			break;
		case "no_match":
			statusEl.classList.add("warn");
			statusEl.innerHTML = `<div class="title">Not an event site</div>${
				state.reason ? `<div class="detail">${escapeHtml(state.reason)}</div>` : ""
			}`;
			break;
		case "found": {
			const { event, count, adapter } = state.data;
			statusEl.classList.add("ok");
			statusEl.innerHTML = `<div class="title">Found ${count} ${
				count === 1 ? "company" : "companies"
			}</div><div class="detail">${escapeHtml(event.name)} · adapter: ${escapeHtml(adapter)}</div>`;
			ingestBtn.hidden = false;
			ingestBtn.textContent = "Ingest to Notion";
			break;
		}
		case "ingesting":
			statusEl.classList.add("ok");
			statusEl.innerHTML = `<div class="title">Found ${state.data.count} companies</div><div class="detail">${escapeHtml(state.data.event.name)}</div>`;
			ingestBtn.hidden = false;
			ingestBtn.disabled = true;
			ingestBtn.innerHTML = '<span class="spinner"></span>Triggering…';
			break;
		case "ingest_done":
			statusEl.classList.add("ok");
			statusEl.innerHTML = `<div class="title">Ingestion triggered</div><div class="detail">Worker is upserting ${state.data.count} companies into Notion. Open the Companies CRM to watch rows appear.</div>`;
			ingestBtn.hidden = false;
			ingestBtn.disabled = true;
			ingestBtn.textContent = "Done";
			break;
		case "error":
			statusEl.classList.add("err");
			statusEl.innerHTML = `<div class="title">Error</div><div class="detail">${escapeHtml(state.message)}</div>`;
			break;
	}
}

function escapeHtml(s: string): string {
	return s
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

checkBtn.addEventListener("click", async () => {
	if (!currentUrl) return;
	state = { kind: "checking" };
	render();
	try {
		const result = await discover(currentUrl);
		if (result.kind === "not_event_site") {
			state = { kind: "no_match", reason: result.reason };
		} else {
			state = { kind: "found", data: result };
		}
	} catch (e) {
		state = { kind: "error", message: (e as Error).message };
	}
	render();
});

ingestBtn.addEventListener("click", async () => {
	if (state.kind !== "found") return;
	const data = state.data;
	state = { kind: "ingesting", data };
	render();
	try {
		await triggerIngest(data.requested_url);
		state = { kind: "ingest_done", data };
	} catch (e) {
		state = { kind: "error", message: (e as Error).message };
	}
	render();
});

init();
