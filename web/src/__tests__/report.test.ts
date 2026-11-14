import { describe, expect, it } from "vitest";
import { buildCitedReport } from "@/lib/report";
import { mockTool } from "@/api/mock";
import { setLang } from "@/lib/i18n";

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

describe("permit check report in Italian", () => {
  it("speaks Italian", async () => {
    setLang("it");
    try {
      const ctx = await mockTool("context_check", { point: [12.49, 41.9] });
      const md = buildCitedReport("Via Nazionale 1", [ctx], { operator: "Op" });
      expect(md).toContain("# Verifica del contesto dell'istanza: Via Nazionale 1");
      expect(md).toContain("- Operatore: Op");
      expect(md).toContain("- Riferimento della pratica: non indicato");
      expect(md).toContain(`Id esecuzione: \`${ctx.run_id}\``);
    } finally {
      setLang("en");
    }
  });
});
