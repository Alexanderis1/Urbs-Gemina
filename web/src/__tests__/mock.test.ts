import { describe, expect, it } from "vitest";
import { TOOL_NAMES } from "@/api/types";
import { mockTool } from "@/api/mock";
import { parseEnvelope } from "@/api/envelope";

describe("sample-data mode", () => {
  for (const name of TOOL_NAMES) {
    it(`${name} returns a valid, synthetic envelope`, async () => {
      const env = parseEnvelope(await mockTool(name, { area: "city" }));
      expect(env.tool).toBe(name);
      expect(env.warnings.join(" ")).toMatch(/sample data/i);
      // Rule: only traffic loops (and hypothetical what-if inputs) may be simulated.
      for (const [layer, kind] of Object.entries(env.data_kinds))
        if (kind === "simulated") expect(["traffic_loops", "what_if"]).toContain(layer);
    });
  }

  it("marks a response synthetic only when it uses loops or a what-if", async () => {
    expect((await mockTool("estimate_field", { area: "city" })).synthetic).toBe(false);
    expect((await mockTool("context_check", { point: [12.5, 41.9] })).synthetic).toBe(false);
    expect((await mockTool("query_layer", { layer: "air_quality", area: "city" })).synthetic).toBe(false);
    expect((await mockTool("query_layer", { layer: "road_speed", area: "city" })).synthetic).toBe(true);
    expect((await mockTool("run_scenario", { kind: "antenna_add", area: "municipio:1", change: {} })).synthetic).toBe(true);
  });

  it("lists only traffic loops as simulated in the honesty panel", async () => {
    const env = await mockTool("data_status", {});
    const layers = (env.result as { layers: { layer: string; kind: string }[] }).layers;
    expect(layers.filter((l) => l.kind === "simulated").map((l) => l.layer)).toEqual(["Traffic loops"]);
    expect(layers.find((l) => l.layer.startsWith("Antenna"))?.kind).toBe("estimated");
    expect(layers.find((l) => l.layer.startsWith("EMF"))?.kind).toBe("estimated");
  });

  it("is deterministic: same inputs give the same run id", async () => {
    const a = await mockTool("estimate_field", { lat: 41.9, lon: 12.5 });
    const b = await mockTool("estimate_field", { lat: 41.9, lon: 12.5 });
    expect(a.run_id).toBe(b.run_id);
  });

  it("never invents a legal threshold", async () => {
    const env = await mockTool("estimate_field", { lat: 41.9, lon: 12.5 });
    expect(JSON.stringify(env.result)).not.toMatch(/limit_v_per_m|threshold_value|"limit"|attention_value_v_per_m/);
  });
});
