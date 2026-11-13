import { describe, expect, it } from "vitest";
import { formatRange, calibrationLabel } from "@/lib/format";

describe("estimate display", () => {
  it("always shows the range with the middle value", () => {
    expect(formatRange({ p5: 0.4, p50: 1.2, p95: 3.05 }, "V/m")).toBe("1.2 V/m (range 0.4 to 3.1)");
  });
  it("labels uncalibrated estimates", () => {
    expect(calibrationLabel("uncalibrated")).toMatch(/not calibrated/i);
    expect(calibrationLabel("calibrated")).toMatch(/calibrated/i);
  });
});
