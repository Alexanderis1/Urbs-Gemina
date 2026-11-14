import { describe, expect, it } from "vitest";
import { planForward } from "../../supabase/functions/_shared/policy";

const env = {
  TOOL_API_URL: "https://api.example/",
  TOOL_API_OFFICE_KEY: "office-key",
  TOOL_API_CITIZEN_KEY: "",
  ORCHESTRATOR_URL: "https://orch.example/ask",
};

describe("edge function policy (tier decided on the server)", () => {
  it("forwards a tool call with the key that matches the user's tier", () => {
    const p = planForward("/tools/query_layer", "office", { layer: "rain" }, env);
    expect(p).toEqual({ ok: true, url: "https://api.example/tools/query_layer", key: "office-key", body: { layer: "rain" } });
  });

  it("serves citizens without the office key", () => {
    const p = planForward("/tools/query_layer", "citizen", { layer: "rain" }, env);
    expect(p.ok && "key" in p && p.key).toBe("");
  });

  it("refuses office-only routes for citizens", () => {
    expect(planForward("/tools/context_check", "citizen", {}, env)).toMatchObject({ ok: false, status: 403 });
    expect(planForward("/sports/manager_update", "citizen", {}, env)).toMatchObject({ ok: false, status: 403 });
  });

  it("refuses unknown tools", () => {
    expect(planForward("/tools/drop_database", "office", {}, env)).toMatchObject({ ok: false, status: 404 });
  });

  it("drops any tier the browser tried to send on /ask and uses the key for the session's tier", () => {
    const p = planForward("/ask", "citizen", { question: "q", tier: "office" }, env);
    expect(p.ok && "body" in p && p.body).toEqual({ question: "q" });
    expect(p.ok && "key" in p && p.key).toBe("");
    expect(p.ok && "url" in p && p.url).toBe("https://orch.example/ask");
  });

  it("strips a tier from tool inputs too", () => {
    const p = planForward("/tools/query_layer", "citizen", { layer: "rain", tier: "office" }, env);
    expect(p.ok && "body" in p && p.body).toEqual({ layer: "rain" });
  });
});

describe("manager updates are stored in Lovable Cloud, not forwarded", () => {
  it("stores a valid update from the office tier", () => {
    const body = { facility_id: "f1", field: "hours", value: "9-21", account_ref: "org:asd-roma", confirmed_at: "2026-11-13T20:00:00Z" };
    expect(planForward("/sports/manager_update", "office", body, env)).toEqual({ ok: true, table: "sports_manager_updates", body });
  });
  it("rejects a person's name as account_ref", () => {
    const body = { facility_id: "f1", field: "hours", value: "9-21", account_ref: "Mario Rossi", confirmed_at: "t" };
    expect(planForward("/sports/manager_update", "office", body, env)).toMatchObject({ ok: false, status: 422 });
  });
});

describe("voice signed URL (private office agent)", () => {
  it("is office only", () => {
    expect(planForward("/voice/signed_url", "citizen", {}, env)).toMatchObject({ ok: false, status: 403 });
  });
  it("asks ElevenLabs for the office agent", () => {
    expect(planForward("/voice/signed_url", "office", {}, env)).toEqual({ ok: true, voice: "office" });
  });
});

describe("live API routes", () => {
  it("forwards the permit report for office only", () => {
    expect(planForward("/reports/permit.md", "citizen", {}, env)).toMatchObject({ ok: false, status: 403 });
    expect(planForward("/reports/permit.md", "office", { place: "x" }, env)).toEqual({
      ok: true,
      url: "https://api.example/reports/permit.md",
      key: "office-key",
      body: { place: "x" },
    });
  });
  it("defaults the orchestrator to the tool API's /ask", () => {
    const p = planForward("/ask", "office", { question: "q" }, { ...env, ORCHESTRATOR_URL: "" });
    expect(p.ok && "url" in p && p.url).toBe("https://api.example/ask");
  });
  it("reads a long-running job with the caller's own key", () => {
    expect(planForward("/jobs/ab12-CD_3", "office", {}, env)).toEqual({
      ok: true,
      url: "https://api.example/jobs/ab12-CD_3",
      key: "office-key",
      body: {},
      method: "GET",
    });
    expect(planForward("/jobs/ab12", "citizen", {}, env)).toMatchObject({ ok: true, key: env.TOOL_API_CITIZEN_KEY });
    expect(planForward("/jobs/../tools/x", "office", {}, env)).toMatchObject({ ok: false, status: 404 });
    expect(planForward("/jobs/", "office", {}, env)).toMatchObject({ ok: false, status: 404 });
  });
  it("knows the permit_report tool", () => {
    expect(planForward("/tools/permit_report", "office", {}, env)).toMatchObject({ ok: true });
  });

  it("lists the ready-made use cases for the caller's tier with a GET upstream", () => {
    expect(planForward("/use_cases", "office", {}, env)).toEqual({
      ok: true,
      url: "https://api.example/use_cases",
      key: "office-key",
      body: {},
      method: "GET",
    });
    expect(planForward("/use_cases", "citizen", {}, env)).toMatchObject({ ok: true, key: "", method: "GET" });
  });
});

describe("citizen report tools", () => {
  const env = { TOOL_API_URL: "https://api.example", TOOL_API_OFFICE_KEY: "o", TOOL_API_CITIZEN_KEY: "", ORCHESTRATOR_URL: "" };
  it("are office only", () => {
    for (const tool of ["signal_events", "verify_signal"]) {
      expect(planForward(`/tools/${tool}`, "citizen", {}, env)).toMatchObject({ ok: false, status: 403 });
      expect(planForward(`/tools/${tool}`, "office", { reports: [] }, env)).toMatchObject({ ok: true, key: "o" });
    }
  });
});

describe("citizen report submission", () => {
  const env = { TOOL_API_URL: "https://api.example", TOOL_API_OFFICE_KEY: "o", TOOL_API_CITIZEN_KEY: "", ORCHESTRATOR_URL: "" };
  const uid = "11111111-1111-1111-1111-111111111111";
  const photo = `${uid}/22222222-2222-2222-2222-222222222222.jpg`;
  const good = { category: "pothole", description: "Buca profonda", lon: 12.48, lat: 41.89, photo_path: photo, photo_source: "camera", photo_gps_distance_m: 0, photo_age_min: 0 };

  it("needs a signed-in resident and goes to screening with the office key", () => {
    expect(planForward("/reports/submit", "citizen", good, env, null)).toMatchObject({ ok: false, status: 401 });
    expect(planForward("/reports/submit", "citizen", good, env, uid)).toMatchObject({ ok: true, screenUrl: "https://api.example/tools/screen_report", key: "o" });
  });
  it("requires GPS, a photo with its own GPS check, and the resident's own folder", () => {
    expect(planForward("/reports/submit", "citizen", { ...good, lat: 45.4 }, env, uid)).toMatchObject({ ok: false });
    expect(planForward("/reports/submit", "citizen", { ...good, photo_path: null }, env, uid)).toMatchObject({ ok: false });
    expect(planForward("/reports/submit", "citizen", { ...good, photo_gps_distance_m: null }, env, uid)).toMatchObject({ ok: false });
    expect(planForward("/reports/submit", "citizen", { ...good, photo_path: `33333333-3333-3333-3333-333333333333/22222222-2222-2222-2222-222222222222.jpg` }, env, uid)).toMatchObject({ ok: false });
  });
  it("public events need no photo; types with kinds need one", () => {
    expect(planForward("/reports/submit", "citizen", { category: "public_event", description: "Concerto in piazza", lon: 12.48, lat: 41.89 }, env, uid)).toMatchObject({ ok: true });
    expect(planForward("/reports/submit", "citizen", { ...good, category: "traffic" }, env, uid)).toMatchObject({ ok: false });
    expect(planForward("/reports/submit", "citizen", { ...good, category: "traffic", subtype: "bus" }, env, uid)).toMatchObject({ ok: true });
  });
  it("the screening tool cannot be called from the browser", () => {
    expect(planForward("/tools/screen_report", "office", {}, env)).toMatchObject({ ok: false });
  });
});
