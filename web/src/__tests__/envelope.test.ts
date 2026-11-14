import { describe, expect, it } from "vitest";
import { parseEnvelope, envelopeBadge, layerBadges, badgeText, extraWarnings } from "@/api/envelope";

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

describe("badge wording", () => {
  it("calls a hypothetical change what-if, and loops simulated", () => {
    expect(badgeText(parseEnvelope({ ...good, data_kinds: { what_if: "simulated", emf: "estimated" } }))).toBe("what-if");
    expect(badgeText(parseEnvelope({ ...good, data_kinds: { traffic_flow: "simulated" } }))).toBe("simulated");
    expect(badgeText(parseEnvelope({ ...good, synthetic: false, data_kinds: { emf: "estimated" } }))).toBe("estimated");
  });

  // Contract additions of 14 Nov 2026 (scenario engine on the live API).
  it("accepts a hypothetical input and shows the run as a what-if", () => {
    const env = parseEnvelope({ ...good, synthetic: false, data_kinds: { terrain: "estimated", river_level: "hypothetical" } });
    expect(badgeText(env)).toBe("what-if");
    // The hypothetical input does not make the data look worse or better: the weakest real input decides.
    expect(envelopeBadge(env)).toBe("estimated");
  });

  it("accepts a source without a retrieval time", () => {
    expect(parseEnvelope({ ...good, sources: [{ id: "copernicus_dem" }] }).sources[0]!.retrieved_at).toBeUndefined();
    expect(() => parseEnvelope({ ...good, sources: [{ id: "x", retrieved_at: 5 }] })).toThrow(/source/);
  });

  it("does not repeat the refusal reason among the warnings", () => {
    const reason = "This simulation runs on at most 3 km2; area 'municipio:1' is 20.0 km2.";
    const env = parseEnvelope({ ...good, status: "refused", reason, warnings: [reason, "Buses are not in the simulation yet."] });
    expect(extraWarnings(env)).toEqual(["Buses are not in the simulation yet."]);
    expect(extraWarnings(parseEnvelope({ ...good, warnings: ["a", "a", "b"] }))).toEqual(["a", "b"]);
  });
});
