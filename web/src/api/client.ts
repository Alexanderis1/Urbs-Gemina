import { parseEnvelope } from "./envelope";
import { mockTool } from "./mock";
import { mockSportTool, SPORT_TOOLS, type SportTool } from "./mockSport";
import type { Envelope, ToolName } from "./types";
import { SUPABASE_URL, supabase } from "@/integrations/supabase/client";

// The browser never talks to the tool API directly: it calls the "tools" edge function (Lovable Cloud),
// which holds the keys, reads the user's tier from the session, and forwards to POST /tools/<name>.
const EXPLICIT = (import.meta.env.VITE_TOOL_PROXY_URL as string | undefined) ?? "";
export const PROXY = (EXPLICIT || (SUPABASE_URL ? `${SUPABASE_URL}/functions/v1/tools` : "")).replace(/\/$/, "");

export const isSampleMode = PROXY === "";

const PUBLISHABLE = (import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined) ?? "";

/** POST to the edge function with the signed-in user's token (or the public key when signed out). */
export async function proxyFetch(path: string, body: unknown): Promise<Response> {
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
    const b = (await res.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(`${tool} failed: ${String(b.detail ?? `HTTP ${res.status}`)}`);
  }
  return parseEnvelope(await res.json()) as Envelope<R>;
}
