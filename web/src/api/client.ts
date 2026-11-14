import { parseEnvelope } from "./envelope";
import { mockTool } from "./mock";
import { mockSportTool, SPORT_TOOLS, type SportTool } from "./mockSport";
import type { Envelope, ToolName } from "./types";
import { SUPABASE_URL, supabase } from "@/integrations/supabase/client";
import { settleJob, type JobReply } from "@/lib/jobs";
import { callWithWakeUp } from "@/lib/retry";
import { getServiceStatus, setServiceStatus } from "@/lib/serviceStatus";

// The browser never talks to the tool API directly: it calls the "tools" edge function (Lovable Cloud),
// which holds the keys, reads the user's tier from the session, and forwards to POST /tools/<name>.
//
// Without Lovable Cloud (local dev, preview) the app talks to the public tool API directly at the citizen
// tier: no key ever reaches the browser. VITE_SAMPLE_MODE=1 switches to built-in sample data instead.
export const PUBLIC_TOOL_API = "https://anzellinialessandroangelo--urbs-gemina-tools-api.us-east.modal.run";
const EXPLICIT = (import.meta.env.VITE_TOOL_PROXY_URL as string | undefined) ?? "";
const SAMPLE = (import.meta.env.VITE_SAMPLE_MODE as string | undefined) === "1";
const DIRECT_ENV = import.meta.env.VITE_TOOL_API_URL as string | undefined;

export const PROXY = (SAMPLE ? "" : EXPLICIT || (SUPABASE_URL ? `${SUPABASE_URL}/functions/v1/tools` : "")).replace(/\/$/, "");
/** Direct, keyless (citizen tier) API base when there is no edge function. */
export const DIRECT = SAMPLE || PROXY ? "" : (DIRECT_ENV || PUBLIC_TOOL_API).replace(/\/$/, "");
export const isDirectMode = DIRECT !== "";
export const isSampleMode = PROXY === "" && DIRECT === "";

const PUBLISHABLE = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) ?? "";

/**
 * POST to the edge function with the signed-in user's token (or the public key when signed out).
 * A request that runs long comes back as a job (HTTP 202): this waits for it and returns the final answer,
 * so callers see one ordinary response (see lib/jobs.ts).
 */
export async function proxyFetch(path: string, body: unknown): Promise<Response> {
  const res = await post(path, body);
  if (res.status !== 202) return res;
  const first: JobReply = { status: 202, body: await res.clone().json().catch(() => null) };
  runningJobs += 1;
  try {
    const last = await settleJob(first, readJob, { onRunning: () => setServiceStatus("working") });
    return last === first ? res : new Response(JSON.stringify(last.body ?? null), { status: last.status, headers: { "content-type": "application/json" } });
  } finally {
    runningJobs -= 1;
    if (runningJobs === 0 && getServiceStatus() === "working") setServiceStatus("ready");
  }
}

/** Long runs being waited for right now (the "working" notice stays until the last one ends). */
let runningJobs = 0;

async function readJob(path: string): Promise<JobReply> {
  const res = DIRECT ? await fetch(`${DIRECT}${path}`) : await post(path, {});
  return { status: res.status, body: await res.json().catch(() => null) };
}

async function post(path: string, body: unknown): Promise<Response> {
  if (DIRECT) {
    // Citizen tier, no credentials. /ask gets the TwinQuestion as is (the API sets the tier from the missing key).
    return fetch(`${DIRECT}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  }
  const token = supabase ? (await supabase.auth.getSession()).data.session?.access_token : undefined;
  const bearer = token ?? PUBLISHABLE;
  return fetch(`${PROXY}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(bearer ? { authorization: `Bearer ${bearer}` } : {}),
      ...(PUBLISHABLE ? { apikey: PUBLISHABLE } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** Tools made for the residents' services (twin/api, use-cases workstream, 14 Nov 2026). */
export const CITIZEN_TOOLS = ["air_here", "emf_here", "city_heatmap", "transport_now", "places_open"] as const;
export type CitizenTool = (typeof CITIZEN_TOOLS)[number];

export async function callTool<R = Record<string, unknown>>(
  tool: ToolName | SportTool | CitizenTool,
  inputs: Record<string, unknown>,
): Promise<Envelope<R>> {
  if (isSampleMode) {
    // The sample data has no citizen tools: the screens then fall back to the layer tools, as they do live.
    if ((CITIZEN_TOOLS as readonly string[]).includes(tool)) throw new Error(`${tool} failed: not in the sample data`);
    const env = (SPORT_TOOLS as readonly string[]).includes(tool)
      ? await mockSportTool(tool as SportTool, inputs)
      : await mockTool(tool as ToolName, inputs);
    return env as Envelope<R>;
  }
  // The service sleeps when idle: after a missing answer it is woken, then asked once more (see lib/retry.ts).
  try {
    const env = await callWithWakeUp(
      () => postTool<R>(tool, inputs),
      async () => void (await postTool("data_status", {})),
      { onWait: () => setServiceStatus("waking") },
    );
    setServiceStatus("ready");
    return env;
  } catch (e) {
    // The call failed for good: stop saying "waking up", the screen shows the failure itself.
    if (getServiceStatus() === "waking") setServiceStatus("unknown");
    throw e;
  }
}

async function postTool<R>(tool: string, inputs: Record<string, unknown>): Promise<Envelope<R>> {
  const res = await proxyFetch(`/tools/${tool}`, inputs);
  if (!res.ok) {
    const b = (await res.json().catch(() => ({}))) as { detail?: unknown; error?: unknown };
    const d = b.detail ?? b.error;
    throw new Error(`${tool} failed: ${typeof d === "string" ? d : d ? JSON.stringify(d) : `HTTP ${res.status}`}`);
  }
  return parseEnvelope(await res.json()) as Envelope<R>;
}

/** Reads a list from the API (GET when talking to it directly; the edge function takes a POST and forwards a GET). */
export async function proxyRead(path: string): Promise<Response> {
  if (DIRECT) return fetch(`${DIRECT}${path}`);
  return post(path, {});
}
