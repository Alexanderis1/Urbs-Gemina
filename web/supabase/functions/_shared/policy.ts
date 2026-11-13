// Pure routing and tier policy for the "tools" edge function. No Deno or Supabase imports,
// so the web test suite (vitest) can test it directly.
//
// The browser never decides its tier. The edge function reads it from the signed-in user's row in
// public.user_roles (no row or not signed in = citizen) and picks the tool API key for that tier.
// The tool API (twin/api) enforces what each tier may see; this file only adds a first gate.

export type Tier = "citizen" | "office";

export interface Env {
  TOOL_API_URL: string;
  TOOL_API_OFFICE_KEY: string;
  /** Optional. Empty = no key, which the tool API serves at the citizen tier. */
  TOOL_API_CITIZEN_KEY: string;
  ORCHESTRATOR_URL: string;
}

export type Plan =
  | { ok: true; url: string; key: string; body: Record<string, unknown> }
  | { ok: true; table: "sports_manager_updates"; body: Record<string, unknown> }
  | { ok: true; voice: "office" }
  | { ok: false; status: number; reason: string };

const TOOLS = new Set([
  "resolve_place",
  "context_check",
  "estimate_field",
  "query_layer",
  "run_scenario",
  "legal_lookup",
  "find_dataset",
  "data_status",
  "permit_report",
  "sports_facilities",
  "sport_coverage",
  "sport_deserts",
]);

/** Routes the citizen tier cannot call at all (the permit check is an office workflow). */
const OFFICE_ONLY = new Set([
  "/tools/context_check",
  "/tools/permit_report",
  "/reports/permit.md",
  "/sports/manager_update",
  "/voice/signed_url",
]);

const EDITABLE = new Set(["disciplines", "hours", "accessibility", "contact", "name"]);

function withoutTier(body: Record<string, unknown>): Record<string, unknown> {
  const { tier: _ignored, ...rest } = body;
  return rest;
}

export function planForward(path: string, tier: Tier, body: Record<string, unknown>, env: Env): Plan {
  if (OFFICE_ONLY.has(path) && tier !== "office") return { ok: false, status: 403, reason: "office tier only" };
  const key = tier === "office" ? env.TOOL_API_OFFICE_KEY : env.TOOL_API_CITIZEN_KEY;

  if (path === "/voice/signed_url") return { ok: true, voice: "office" };

  const base = env.TOOL_API_URL.replace(/\/$/, "");

  if (path === "/ask") {
    // TwinQuestion: the tier is decided here, from the session; anything the browser sent is dropped.
    // The orchestrator runs inside the tool API (/ask) unless ORCHESTRATOR_URL points elsewhere.
    const url = env.ORCHESTRATOR_URL || `${base}/ask`;
    // The tier travels as the API key (office key or none); the live /ask rejects extra body fields.
    return { ok: true, url, key, body: withoutTier(body) };
  }

  if (path === "/reports/permit.md") return { ok: true, url: `${base}/reports/permit.md`, key, body: withoutTier(body) };

  if (path === "/sports/manager_update") {
    const { facility_id, field, account_ref, confirmed_at } = body;
    if (typeof facility_id !== "string" || typeof field !== "string" || typeof confirmed_at !== "string")
      return { ok: false, status: 422, reason: "facility_id, field and confirmed_at are required" };
    if (!EDITABLE.has(field)) return { ok: false, status: 422, reason: `field "${field}" cannot be edited` };
    if (typeof account_ref !== "string" || !/^org:[a-z0-9-]+$/.test(account_ref))
      return { ok: false, status: 422, reason: "account_ref must be an organisational account (org:<slug>)" };
    return { ok: true, table: "sports_manager_updates", body };
  }

  const m = /^\/tools\/([a-z_]+)$/.exec(path);
  if (!m || !TOOLS.has(m[1]!)) return { ok: false, status: 404, reason: "unknown route" };
  return { ok: true, url: `${base}/tools/${m[1]}`, key, body: withoutTier(body) };
}
