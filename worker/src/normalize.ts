// CRM option normalization. The Companies CRM is a user-owned database; the
// curator hands us free-form strings ("Tech", "tech/software"). These helpers
// map those onto the exact option names that exist in the CRM schema so the
// `select` properties round-trip cleanly.

const INDUSTRY_OPTIONS = [
	{ name: "Tech / Software" },
	{ name: "Healthcare / Pharma" },
	{ name: "Finance / VC" },
	{ name: "Legal" },
	{ name: "Consulting" },
	{ name: "Education / Research" },
	{ name: "Hospitality / Events" },
	{ name: "Government / Non-profit" },
	{ name: "Gaming / Entertainment" },
	{ name: "Real Estate" },
	{ name: "Other" },
];

const WEALTH_TIER_OPTIONS = [
	{ name: "💎 Mega Cap" },
	{ name: "🏢 Large Enterprise" },
	{ name: "📈 Mid-Market" },
	{ name: "🚀 Funded Startup" },
	{ name: "🎓 Education / Research" },
	{ name: "🏛️ Government / Non-profit" },
	{ name: "🤝 Hospitality Partner" },
	{ name: "❓ SMB / Personal" },
];

function matchOption<T extends { name: string }>(
	value: string | null | undefined,
	options: T[],
): string | undefined {
	if (!value) return undefined;
	const v = value.trim().toLowerCase();
	if (!v) return undefined;
	const exact = options.find((o) => o.name.toLowerCase() === v);
	if (exact) return exact.name;
	const partial = options.find((o) => {
		const n = o.name.toLowerCase();
		return n.includes(v) || v.includes(n);
	});
	return partial?.name;
}

export function normalizeIndustryName(v?: string | null): string | undefined {
	return matchOption(v, INDUSTRY_OPTIONS);
}

export function normalizeWealthTierName(v?: string | null): string | undefined {
	if (!v) return undefined;
	const map: Record<string, string> = {
		mega_cap: "💎 Mega Cap",
		mega: "💎 Mega Cap",
		large_enterprise: "🏢 Large Enterprise",
		large: "🏢 Large Enterprise",
		mid_market: "📈 Mid-Market",
		mid: "📈 Mid-Market",
		midmarket: "📈 Mid-Market",
		funded_startup: "🚀 Funded Startup",
		startup: "🚀 Funded Startup",
		education: "🎓 Education / Research",
		research: "🎓 Education / Research",
		government: "🏛️ Government / Non-profit",
		non_profit: "🏛️ Government / Non-profit",
		nonprofit: "🏛️ Government / Non-profit",
		hospitality: "🤝 Hospitality Partner",
		hospitality_partner: "🤝 Hospitality Partner",
		smb: "❓ SMB / Personal",
		personal: "❓ SMB / Personal",
	};
	const key = v.trim().toLowerCase().replace(/[-\s]+/g, "_");
	return map[key] ?? matchOption(v, WEALTH_TIER_OPTIONS);
}

export function normalizePriorityName(v?: string | null): string | undefined {
	if (!v) return undefined;
	const k = v.trim().toLowerCase();
	if (k === "high") return "High";
	if (k === "mid" || k === "medium") return "Mid";
	if (k === "low") return "Low";
	return undefined;
}
