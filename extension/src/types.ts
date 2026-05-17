export type DiscoverEvent = {
	name: string;
	platform: string;
	platform_event_id: string;
	source_url: string;
	venue: string | null;
	start_date: string | null;
	end_date: string | null;
};

export type DiscoverSuccess = {
	kind: "found";
	event: DiscoverEvent;
	count: number;
	adapter: string;
	requested_url: string;
	resolved_url: string;
	was_resolved: boolean;
};

export type DiscoverMiss = { kind: "not_event_site"; reason?: string };

export type DiscoverResult = DiscoverSuccess | DiscoverMiss;
