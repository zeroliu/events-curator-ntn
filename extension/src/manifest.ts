import { defineManifest } from "@crxjs/vite-plugin";

export default defineManifest({
	manifest_version: 3,
	name: "Show Me Math",
	version: "0.1.0",
	description:
		"Check whether the current site is an event site and ingest its companies into the Notion Companies CRM.",
	action: {
		default_popup: "src/popup.html",
		default_title: "Show Me Math",
	},
	permissions: ["activeTab"],
	host_permissions: ["http://localhost/*", "http://127.0.0.1/*", "https://*/*"],
});
