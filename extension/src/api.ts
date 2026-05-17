import type { DiscoverResult } from "./types";

const CURATOR_BASE_URL = String(import.meta.env.VITE_CURATOR_BASE_URL ?? "").replace(/\/+$/, "");
const WORKER_WEBHOOK_URL = String(import.meta.env.VITE_WORKER_WEBHOOK_URL ?? "");
const WORKER_WEBHOOK_SECRET = String(import.meta.env.VITE_WORKER_WEBHOOK_SECRET ?? "");

function requireCuratorBaseUrl(): string {
	if (!CURATOR_BASE_URL) {
		throw new Error("VITE_CURATOR_BASE_URL is not set — rebuild after filling in .env");
	}
	return CURATOR_BASE_URL;
}

export async function discover(url: string): Promise<DiscoverResult> {
	const base = requireCuratorBaseUrl();
	let res: Response;
	try {
		res = await fetch(`${base}/events/discover`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ url }),
		});
	} catch (e) {
		throw new Error(`Curator API unreachable: ${(e as Error).message}`);
	}

	if (res.status === 404) {
		const body = await res.json().catch(() => null);
		const reason =
			body && typeof body.detail === "object" && body.detail !== null
				? String((body.detail as { message?: unknown }).message ?? "")
				: undefined;
		return { kind: "not_event_site", reason };
	}
	if (!res.ok) {
		const text = await res.text().catch(() => "");
		throw new Error(`discover failed (${res.status}): ${text.slice(0, 300)}`);
	}
	const data = (await res.json()) as Omit<
		Extract<DiscoverResult, { kind: "found" }>,
		"kind"
	>;
	return { kind: "found", ...data };
}

export async function triggerIngest(url: string): Promise<void> {
	if (!WORKER_WEBHOOK_URL) {
		throw new Error("VITE_WORKER_WEBHOOK_URL is not set — deploy the worker first, then fill .env");
	}
	if (!WORKER_WEBHOOK_SECRET) {
		throw new Error("VITE_WORKER_WEBHOOK_SECRET is not set");
	}
	const res = await fetch(WORKER_WEBHOOK_URL, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Authorization: `Bearer ${WORKER_WEBHOOK_SECRET}`,
		},
		body: JSON.stringify({ url }),
	});
	if (!res.ok) {
		const text = await res.text().catch(() => "");
		throw new Error(`webhook failed (${res.status}): ${text.slice(0, 300)}`);
	}
}

export async function getActiveTabUrl(): Promise<string | null> {
	const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
	const url = tab?.url ?? null;
	if (!url) return null;
	if (!/^https?:\/\//.test(url)) return null;
	return url;
}
