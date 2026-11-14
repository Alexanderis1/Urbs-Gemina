import { parseEnvelope } from "./envelope";
import { mockTool } from "./mock";
import { mockSportTool, SPORT_TOOLS, type SportTool } from "./mockSport";
import type { Envelope, ToolName } from "./types";
import { SUPABASE_URL, supabase } from "@/integrations/supabase/client";

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

/** POST to the edge function with the signed-in user's token (or the public key when signed out). */
export async function proxyFetch(path: string, body: unknown): Promise<Response> {
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

export async function callTool<R = Record<string, unknown>>(
  tool: ToolName | SportTool,
  inputs: Record<string, unknown>,
): Promise<Envelope<R>> {
  if (isSampleMode) {
    const env = (SPORT_TOOLS as readonly string[]).includes(tool)
      ? await mockSportTool(tool as SportTool, inputs)
      : await mockTool(tool as ToolName, inputs);
    return env as Envelope<R>;
  }
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
  return proxyFetch(path, {});
}
