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
        if (kind === "simulated") expect(["traffic_flow", "what_if"]).toContain(layer);
    });
  }

  it("marks a response synthetic only when it uses loops or a what-if", async () => {
    expect((await mockTool("estimate_field", { area: "city" })).synthetic).toBe(false);
    expect((await mockTool("context_check", { point: [12.5, 41.9] })).synthetic).toBe(false);
    expect((await mockTool("query_layer", { layer: "rain", area: "city" })).synthetic).toBe(false);
    expect((await mockTool("query_layer", { layer: "traffic_flow", area: "city" })).synthetic).toBe(true);
    expect((await mockTool("run_scenario", { kind: "antenna_add", area: "municipio:1", change: {} })).synthetic).toBe(true);
  });

  it("lists only traffic loops as simulated in the honesty panel", async () => {
    const env = await mockTool("data_status", {});
    const layers = (env.result as { layers: unknown[] }).layers;
    const ls = layers as unknown as { layer: string; data_kind: string }[];
    expect(ls.filter((l) => l.data_kind === "simulated").map((l) => l.layer)).toEqual(["traffic_flow"]);
    expect(ls.find((l) => l.layer === "antenna_register")?.data_kind).toBe("estimated");
    expect(ls.find((l) => l.layer === "emf_baseline")?.data_kind).toBe("estimated");
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
