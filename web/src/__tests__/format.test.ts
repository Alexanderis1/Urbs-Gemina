import { describe, expect, it } from "vitest";
import { formatRange, calibrationLabel } from "@/lib/format";

describe("estimate display", () => {
  it("always shows the range with the middle value", () => {
    expect(formatRange({ p5: 0.4, p50: 1.2, p95: 3.05 }, "V/m")).toBe("1.2 V/m (range 0.4 to 3.1)");
  });
  it("groups thousands in large counts", () => {
    expect(formatRange({ p5: 1200, p50: 4728, p95: 13077 }, "residents")).toBe("4,728 residents (range 1,200 to 13,077)");
  });
  it("keeps small values precise and drops decimals on large ones", () => {
    expect(formatRange({ p5: 0.143, p50: 0.259, p95: 0.429 }, "")).toBe("0.259 (range 0.143 to 0.429)");
    expect(formatRange({ p5: 0, p50: 68152.193, p95: 116945.259 }, "m³")).toBe("68,152 m³ (range 0 to 116,945)");
  });
  it("labels uncalibrated estimates", () => {
    expect(calibrationLabel("uncalibrated")).toMatch(/not calibrated/i);
    expect(calibrationLabel("calibrated")).toMatch(/calibrated/i);
  });
});
