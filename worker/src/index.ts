import { Worker, WebhookVerificationError } from "@notionhq/workers";

import { runIngest } from "./ingest-flow.js";
import { registerIngestEvent } from "./tools/ingest-event.js";

const worker = new Worker();
export default worker;

registerIngestEvent(worker);

// Webhook the Chrome extension calls. Same logic as the `ingestEvent` tool,
// just triggered via an authenticated HTTPS POST instead of a Custom Agent.
worker.webhook("ingestFromExtension", {
	title: "Ingest event from extension",
	description:
		"Triggered by the events-curator Chrome extension. Body must be JSON " +
		"of shape { url: string }. Authorization header must carry the shared " +
		"EXTENSION_WEBHOOK_SECRET as a bearer token.",
	execute: async (events, { notion }) => {
		const secret = process.env.EXTENSION_WEBHOOK_SECRET;
		if (!secret) {
			throw new WebhookVerificationError("EXTENSION_WEBHOOK_SECRET not set");
		}
		for (const evt of events) {
			const auth = evt.headers["authorization"] ?? evt.headers["Authorization"];
			if (auth !== `Bearer ${secret}`) {
				throw new WebhookVerificationError("invalid extension webhook secret");
			}
			const url = typeof evt.body?.url === "string" ? evt.body.url : null;
			if (!url) {
				throw new Error("webhook body missing required `url` string");
			}
			await runIngest(url, notion);
		}
	},
});
