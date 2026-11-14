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
  | { ok: true; url: string; key: string; body: Record<string, unknown>; method?: "GET" }
  | { ok: true; table: "sports_manager_updates"; body: Record<string, unknown> }
  | { ok: true; voice: "office" }
  | { ok: true; submit: ReportRow; screenUrl: string; key: string }
  | { ok: false; status: number; reason: string };

// ---- Citizen reports (Alessandro, 14 Nov 2026) --------------------------------------------------------------
// Reports are stored only by this function, after a Claude screening (tool screen_report): the browser cannot
// write the table directly, so the screening cannot be skipped. GPS is required; a photo is required except for
// public events, and its own GPS/time check must be present when there is one.

export const REPORT_TYPES: Record<string, { photo: boolean; subtypes: string[] }> = {
  flood: { photo: true, subtypes: ["flood", "sewer"] },
  pothole: { photo: true, subtypes: [] },
  traffic: { photo: true, subtypes: ["incident", "congestion", "bus", "metro"] },
  roadworks: { photo: true, subtypes: [] },
  public_event: { photo: false, subtypes: [] },
};

export interface ReportRow {
  category: string;
  subtype: string | null;
  description: string;
  lon: number;
  lat: number;
  gps_accuracy_m: number | null;
  photo_path: string | null;
  photo_source: "camera" | "gallery" | null;
  photo_gps_distance_m: number | null;
  photo_age_min: number | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Checks a report sent by a signed-in resident. `userId` must own the photo's folder. */
export function validateReport(body: Record<string, unknown>, userId: string | null): { ok: true; row: ReportRow } | { ok: false; status: number; reason: string } {
  if (!userId) return { ok: false, status: 401, reason: "sign in first" };
  const type = REPORT_TYPES[String(body.category)];
  if (!type) return { ok: false, status: 422, reason: "unknown report type" };
  const subtype = typeof body.subtype === "string" && type.subtypes.includes(body.subtype) ? body.subtype : null;
  if (type.subtypes.length && !subtype) return { ok: false, status: 422, reason: "choose what kind of problem it is" };
  const description = typeof body.description === "string" ? body.description.trim() : "";
  if (description.length < 3 || description.length > 280) return { ok: false, status: 422, reason: "description must be 3 to 280 characters" };
  const lon = num(body.lon);
  const lat = num(body.lat);
  if (lon === null || lat === null || lon < 12.0 || lon > 13.1 || lat < 41.4 || lat > 42.4)
    return { ok: false, status: 422, reason: "device GPS position in Rome is required" };
  const path = typeof body.photo_path === "string" ? body.photo_path : null;
  if (path !== null && !new RegExp(`^${userId}/[0-9a-f-]{36}\\.jpg$`).test(path)) return { ok: false, status: 422, reason: "photo path not allowed" };
  if (type.photo && !path) return { ok: false, status: 422, reason: "a photo is required for this report" };
  const dist = num(body.photo_gps_distance_m);
  const age = num(body.photo_age_min);
  const source = body.photo_source === "camera" || body.photo_source === "gallery" ? body.photo_source : null;
  if (path && (dist === null || age === null || source === null)) return { ok: false, status: 422, reason: "the photo's own GPS and time are required" };
  return {
    ok: true,
    row: {
      category: String(body.category),
      subtype,
      description,
      lon,
      lat,
      gps_accuracy_m: num(body.gps_accuracy_m),
      photo_path: path,
      photo_source: path ? source : null,
      photo_gps_distance_m: path ? dist : null,
      photo_age_min: path ? age : null,
    },
  };
}

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
  "signal_events",
  "verify_signal",
]);

/** Routes the citizen tier cannot call at all (the permit check is an office workflow). */
const OFFICE_ONLY = new Set([
  "/tools/context_check",
  "/tools/permit_report",
  "/reports/permit.md",
  "/sports/manager_update",
  "/voice/signed_url",
  // Citizen reports: only the operations room sees merged events; the check costs a Claude + Exa call.
  "/tools/signal_events",
  "/tools/verify_signal",
]);

const EDITABLE = new Set(["disciplines", "hours", "accessibility", "contact", "name"]);

function withoutTier(body: Record<string, unknown>): Record<string, unknown> {
  const { tier: _ignored, ...rest } = body;
  return rest;
}

export function planForward(path: string, tier: Tier, body: Record<string, unknown>, env: Env, userId: string | null = null): Plan {
  if (OFFICE_ONLY.has(path) && tier !== "office") return { ok: false, status: 403, reason: "office tier only" };
  const key = tier === "office" ? env.TOOL_API_OFFICE_KEY : env.TOOL_API_CITIZEN_KEY;

  if (path === "/voice/signed_url") return { ok: true, voice: "office" };

  const base = env.TOOL_API_URL.replace(/\/$/, "");

  if (path === "/reports/submit") {
    // Any signed-in resident. Screening runs with the office key because the tool is not open to the public.
    const checked = validateReport(body, userId);
    if (!checked.ok) return checked;
    return { ok: true, submit: checked.row, screenUrl: `${base}/tools/screen_report`, key: env.TOOL_API_OFFICE_KEY };
  }

  if (path === "/ask") {
    // TwinQuestion: the tier is decided here, from the session; anything the browser sent is dropped.
    // The orchestrator runs inside the tool API (/ask) unless ORCHESTRATOR_URL points elsewhere.
    const url = env.ORCHESTRATOR_URL || `${base}/ask`;
    // The tier travels as the API key (office key or none); the live /ask rejects extra body fields.
    return { ok: true, url, key, body: withoutTier(body) };
  }

  // Ready-made use cases the caller's tier may run (the API filters by the key). The browser POSTs here; upstream is a GET.
  if (path === "/use_cases") return { ok: true, url: `${base}/use_cases`, key, body: {}, method: "GET" };

  // A request that runs long answers 202 with a job id; the browser then reads the job here until it is done.
  // Upstream is a GET with the same key as the request that started the job.
  const job = /^\/jobs\/([A-Za-z0-9_-]{1,128})$/.exec(path);
  if (job) return { ok: true, url: `${base}/jobs/${job[1]}`, key, body: {}, method: "GET" };

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
