import { parseEnvelope } from "./envelope";
import { mockTool } from "./mock";
import { mockSportTool, SPORT_TOOLS, type SportTool } from "./mockSport";
import type { Envelope, ToolName } from "./types";

// The browser never talks to the tool API directly: it calls an edge function (Lovable Cloud / Supabase)
// that holds the keys and the user's tier, and forwards to POST /tools/<name>.
export const PROXY = (import.meta.env.VITE_TOOL_PROXY_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export const isSampleMode = PROXY === "";

export async function callTool<R = Record<string, unknown>>(
  tool: ToolName | SportTool,
  inputs: Record<string, unknown>,
  authToken?: string,
): Promise<Envelope<R>> {
  if (isSampleMode) {
    const env = (SPORT_TOOLS as readonly string[]).includes(tool)
      ? await mockSportTool(tool as SportTool, inputs)
      : await mockTool(tool as ToolName, inputs);
    return env as Envelope<R>;
  }
  const res = await fetch(`${PROXY}/tools/${tool}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(authToken ? { authorization: `Bearer ${authToken}` } : {}) },
    body: JSON.stringify(inputs),
  });
  if (!res.ok) throw new Error(`${tool} failed: HTTP ${res.status}`);
  return parseEnvelope(await res.json()) as Envelope<R>;
}
