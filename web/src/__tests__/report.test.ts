import { describe, expect, it } from "vitest";
import { buildCitedReport } from "@/lib/report";
import { mockTool } from "@/api/mock";

describe("permit check report", () => {
  it("cites every run id and source and flags synthetic data", async () => {
    const ctx = await mockTool("context_check", { point: [12.49, 41.9] });
    const field = await mockTool("estimate_field", { area: "city", variant: { operator: "Op", height_m: 30 } });
    const md = buildCitedReport("Via Nazionale 1", [ctx, field], { operator: "Op", height_m: "30" });
    expect(md).toContain("Operator: Op");
    expect(md).toContain(ctx.run_id);
    expect(md).toContain(field.run_id);
    for (const s of [...ctx.sources, ...field.sources]) expect(md).toContain(s.id);
    expect(md).toMatch(/sample data/i);
    expect(md).toMatch(/context, not a prohibition/i);
  });
});
