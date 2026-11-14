// Lovable Cloud edge function "tools": the only way the browser reaches the tool API and the orchestrator.
// It holds the API keys (secrets), reads the user's tier from public.user_roles, and forwards.
//
// Secrets in Lovable Cloud: URBS_OFFICE_KEY (office key of the tool API), ELEVENLABS_API_KEY.
// Optional: TOOL_API_URL (default: the public Modal API), TOOL_API_CITIZEN_KEY, ORCHESTRATOR_URL (default <api>/ask),
// ELEVENLABS_OFFICE_AGENT_ID (default below).
// SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
import { createClient } from "npm:@supabase/supabase-js@2.46.1";
import { planForward, reportLimit, type Env, type Tier } from "../_shared/policy.ts";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, x-client-info, apikey, content-type",
  "access-control-allow-methods": "POST, OPTIONS",
};

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "content-type": "application/json" } });

async function tierOf(req: Request): Promise<{ tier: Tier; userId: string | null }> {
  const auth = req.headers.get("authorization") ?? "";
  const url = Deno.env.get("SUPABASE_URL")!;
  const userClient = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, { global: { headers: { authorization: auth } } });
  const { data } = await userClient.auth.getUser();
  if (!data.user) return { tier: "citizen", userId: null };
  // Read with the service role so a user cannot spoof the row; RLS still blocks writes from the browser.
  const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: row } = await admin.from("user_roles").select("tier").eq("user_id", data.user.id).maybeSingle();
  return { tier: row?.tier === "office" ? "office" : "citizen", userId: data.user.id };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return json(405, { reason: "POST only" });

  const path = new URL(req.url).pathname.replace(/^(?:\/functions\/v1)?\/tools(?=\/)/, "");
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return json(400, { reason: "body must be JSON" });
  }

  const { tier, userId } = await tierOf(req);
  const env: Env = {
    TOOL_API_URL: Deno.env.get("TOOL_API_URL") || "https://anzellinialessandroangelo--urbs-gemina-tools-api.us-east.modal.run",
    TOOL_API_OFFICE_KEY: Deno.env.get("URBS_OFFICE_KEY") ?? Deno.env.get("TOOL_API_OFFICE_KEY") ?? "",
    TOOL_API_CITIZEN_KEY: Deno.env.get("TOOL_API_CITIZEN_KEY") ?? "",
    ORCHESTRATOR_URL: Deno.env.get("ORCHESTRATOR_URL") ?? "",
  };
  const plan = planForward(path, tier, body, env, userId);
  if (!plan.ok) return json(plan.status, { detail: plan.reason });

  if ("voice" in plan) {
    const agent = Deno.env.get("ELEVENLABS_OFFICE_AGENT_ID") ?? "agent_5801m7b8bx9gedj9fj7r1e3s54vh";
    const key = Deno.env.get("ELEVENLABS_API_KEY") ?? "";
    if (!key) return json(503, { detail: "voice not configured" });
    const r = await fetch(
      `https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=${encodeURIComponent(agent)}`,
      { headers: { "xi-api-key": key } },
    );
    if (!r.ok) return json(502, { detail: `ElevenLabs HTTP ${r.status}` });
    const { signed_url } = (await r.json()) as { signed_url: string };
    return json(200, { signed_url });
  }

  if ("submit" in plan) {
    // Citizen report: rate limit, screen with Claude (tool screen_report), then store. Rejected reports are kept
    // for audit with status 'rejected' and never shown on the staff map; their photo is deleted.
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    // Rejected reports count too, so a stolen or abusive account cannot keep trying.
    const sent = async (ms: number) =>
      (await admin.from("citizen_reports").select("id", { count: "exact", head: true }).eq("user_id", userId)
        .gte("created_at", new Date(Date.now() - ms).toISOString())).count ?? 0;
    const limited = reportLimit(await sent(3600_000), await sent(86_400_000));
    if (limited) return json(limited.status, { detail: limited.detail });
    let photoUrl: string | null = null;
    if (plan.submit.photo_path) {
      const { data } = await admin.storage.from("report-photos").createSignedUrl(plan.submit.photo_path, 300);
      if (!data?.signedUrl) return json(422, { detail: "photo not found: upload it first" });
      photoUrl = data.signedUrl;
    }
    let screening: Record<string, unknown> = { verdict: "review", reasons: [], photo: "no_photo", note: "screening not available" };
    if (plan.key) {
      const r = await fetch(plan.screenUrl, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${plan.key}` },
        body: JSON.stringify({ category: plan.submit.category, subtype: plan.submit.subtype, text: plan.submit.description, photo_url: photoUrl }),
      }).catch(() => null);
      const env = r?.ok ? ((await r.json()) as { status?: string; result?: Record<string, unknown> }) : null;
      if (env?.status === "ok" && env.result) screening = env.result;
    }
    const rejected = screening.verdict === "reject";
    if (rejected && plan.submit.photo_path) await admin.storage.from("report-photos").remove([plan.submit.photo_path]);
    const { data, error } = await admin
      .from("citizen_reports")
      .insert({ ...plan.submit, photo_path: rejected ? null : plan.submit.photo_path, user_id: userId, status: rejected ? "rejected" : "new", screening })
      .select("id")
      .single();
    if (error) return json(422, { detail: error.message });
    return json(200, { stored: true, id: data.id, verdict: screening.verdict, reasons: screening.reasons ?? [], note: screening.note ?? "" });
  }

  if ("table" in plan) {
    const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { error } = await admin.from(plan.table).insert({ ...plan.body, user_id: userId });
    return error ? json(422, { detail: error.message }) : json(200, { stored: true });
  }

  if (!plan.url) return json(503, { detail: "back end not configured" });
  const auth = plan.key ? { authorization: `Bearer ${plan.key}` } : {};
  const upstream =
    plan.method === "GET"
      ? await fetch(plan.url, { headers: auth })
      : await fetch(plan.url, { method: "POST", headers: { "content-type": "application/json", ...auth }, body: JSON.stringify(plan.body) });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { ...CORS, "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
});
