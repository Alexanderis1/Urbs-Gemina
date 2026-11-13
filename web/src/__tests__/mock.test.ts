import { describe, expect, it } from "vitest";
import { TOOL_NAMES } from "@/api/types";
import { mockTool } from "@/api/mock";
import { parseEnvelope } from "@/api/envelope";

describe("sample-data mode", () => {
  for (const name of TOOL_NAMES) {
    it(`${name} returns a valid, synthetic envelope`, async () => {
      const env = parseEnvelope(await mockTool(name, { area: "city" }));
      expect(env.tool).toBe(name);
      expect(env.synthetic).toBe(true);
      expect(env.warnings.join(" ")).toMatch(/sample data/i);
      expect(Object.values(env.data_kinds).every((k) => k === "simulated")).toBe(true);
    });
  }

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
