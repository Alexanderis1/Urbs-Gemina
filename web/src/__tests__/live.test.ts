// Adapters for the live tool API (fixtures are trimmed real responses from 13 Nov 2026).
import { describe, expect, it } from "vitest";
import live from "./fixtures/live_api.json";
import { parseEnvelope } from "@/api/envelope";
import { normalizeLayer } from "@/lib/layers";
import { contextRows, contextSummary } from "@/lib/context";

const env = (k: keyof typeof live) => parseEnvelope(live[k]);

describe("live envelopes parse", () => {
  for (const k of Object.keys(live) as (keyof typeof live)[]) it(k, () => expect(env(k).run_id).toHaveLength(64));
});

describe("query_layer results become map data", () => {
  it("belief layers are H3 cells with a range", () => {
    const d = normalizeLayer(env("rain").result);
    expect(d.kind).toBe("hex");
    expect(d.unit).toBe("mm/h");
    expect(d.items[0]).toMatchObject({ h3: "891e8050103ffff", value: 0.047 });
    expect(d.items[0]!.uncertainty).toBeCloseTo(0.698);
  });
  it("observations are points with the main value and its sigma", () => {
    const d = normalizeLayer(env("traffic_flow").result);
    expect(d.kind).toBe("points");
    expect(d.metric).toBe("intensity");
    expect(d.items[0]).toMatchObject({ position: [12.445914, 41.906322], value: 627.5, uncertainty: 50.2, synthetic: true });
  });
  it("aggregates are counts per cell", () => {
    const d = normalizeLayer(env("antenna_register").result);
    expect(d.kind).toBe("points");
    expect(d.metric).toBe("count");
    expect(d.cellM).toBe(500);
  });
  it("feature layers are points", () => {
    const d = normalizeLayer(env("schools_state").result);
    expect(d.kind).toBe("points");
    expect(d.items[0]!.position).toEqual([12.464869, 41.91866104]);
  });
  it("EMF grid uses the electric field", () => {
    expect(normalizeLayer(env("emf_baseline").result).metric).toBe("electricField");
  });
});

describe("context_check groups", () => {
  it("lists every hit with its layer label, nearest first", () => {
    const rows = contextRows(env("context_check").result);
    expect(rows[0]).toMatchObject({ layerLabel: "UNESCO World Heritage site", name: "Centro storico di Roma", distance_m: 0 });
    expect(rows.map((r) => r.distance_m)).toEqual([...rows.map((r) => r.distance_m)].sort((a, b) => a - b));
  });
  it("counts layers checked and layers not available", () => {
    const s = contextSummary(env("context_check").result);
    expect(s.notAvailable).toBe(5);
    expect(s.sensitiveHits).toBe(0);
  });
});
