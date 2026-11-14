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
