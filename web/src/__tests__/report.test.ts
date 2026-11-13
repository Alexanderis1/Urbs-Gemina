import { describe, expect, it } from "vitest";
import { buildCitedReport } from "@/lib/report";
import { mockTool } from "@/api/mock";

describe("permit check report", () => {
  it("cites every run id and source and flags synthetic data", async () => {
    const ctx = await mockTool("context_check", { lat: 41.9, lon: 12.49, radius_m: 300 });
    const field = await mockTool("estimate_field", { lat: 41.9, lon: 12.49 });
    const md = buildCitedReport("Via Nazionale 1", [ctx, field]);
    expect(md).toContain(ctx.run_id);
    expect(md).toContain(field.run_id);
    for (const s of [...ctx.sources, ...field.sources]) expect(md).toContain(s.id);
    expect(md).toMatch(/SIMULATED/);
    expect(md).toMatch(/context, not a prohibition/i);
  });
});
