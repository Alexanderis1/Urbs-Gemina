import { describe, expect, it } from "vitest";
import { parseEnvelope, envelopeBadge, layerBadges } from "@/api/envelope";

const good = {
  run_id: "a".repeat(64),
  tool: "context_check",
  inputs: { area: "city" },
  result: {},
  data_kinds: { schools: "real", antennas: "simulated" },
  sources: [{ id: "roma_wfs", retrieved_at: "2026-11-13T10:00:00Z" }],
  synthetic: true,
  warnings: [],
};

describe("tool response envelope", () => {
  it("accepts a well-formed envelope", () => {
    expect(parseEnvelope(good).run_id).toBe(good.run_id);
  });

  it("rejects an envelope without run_id (no number without a run id)", () => {
    const { run_id: _drop, ...bad } = good;
    expect(() => parseEnvelope(bad)).toThrow(/run_id/);
  });

  it("rejects an unknown data kind", () => {
    expect(() => parseEnvelope({ ...good, data_kinds: { x: "guess" } })).toThrow(/data kind/);
  });

  it("shows SIMULATED when the envelope is synthetic, even if layers say real", () => {
    expect(envelopeBadge({ ...parseEnvelope(good), data_kinds: { a: "real" } })).toBe("simulated");
  });

  it("shows the weakest kind when nothing is synthetic", () => {
    const env = parseEnvelope({ ...good, synthetic: false, data_kinds: { a: "real", b: "estimated" } });
    expect(envelopeBadge(env)).toBe("estimated");
  });

  it("lists one badge per layer", () => {
    expect(layerBadges(parseEnvelope(good))).toEqual([
      ["antennas", "simulated"],
      ["schools", "real"],
    ]);
  });
});

describe("envelope additions (status, reason, cached, not_available)", () => {
  it("accepts a not_available result with a reason", () => {
    const env = parseEnvelope({ ...good, status: "not_available", reason: "layer not loaded", cached: false, data_kinds: { emf: "not_available" } });
    expect(env.status).toBe("not_available");
    expect(env.reason).toBe("layer not loaded");
  });
  it("treats a missing status as ok (older tools)", () => {
    expect(parseEnvelope(good).status ?? "ok").toBe("ok");
  });
  it("rejects an unknown status or a non-ok status without reason", () => {
    expect(() => parseEnvelope({ ...good, status: "maybe" })).toThrow(/status/);
    expect(() => parseEnvelope({ ...good, status: "refused" })).toThrow(/reason/);
  });
});
