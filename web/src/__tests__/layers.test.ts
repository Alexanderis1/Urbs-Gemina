import { describe, expect, it } from "vitest";
import { describeItem, formatValue, valueExtent } from "@/lib/layers";

describe("formatValue", () => {
  it("keeps at most three significant digits", () => {
    expect(formatValue(1234)).toBe("1,230");
    expect(formatValue(0.37)).toBe("0.37");
    expect(formatValue(0.000123456)).toBe("0.000123");
    expect(formatValue(12)).toBe("12");
    expect(formatValue(0)).toBe("0");
    expect(formatValue(-3.14159)).toBe("-3.14");
  });
});

describe("valueExtent", () => {
  it("returns the real minimum and maximum", () => {
    expect(valueExtent([{ value: 3 }, { value: -1 }, { value: 7 }])).toEqual({ min: -1, max: 7 });
  });
  it("is null when there is nothing on screen", () => {
    expect(valueExtent([])).toBeNull();
  });
});

describe("describeItem", () => {
  it("shows a belief cell with its unit, range and spread", () => {
    const d = describeItem({ h3: "x", value: 1.234, uncertainty: 0.5, p5: 0.4, p95: 2.1 }, { metric: "rain", unit: "mm/h" });
    expect(d.lines).toEqual(["Rain: 1.23 mm/h", "Range 0.4 to 2.1 mm/h", "Uncertainty ± 0.5 mm/h"]);
  });
  it("shows only what an observation carries", () => {
    const d = describeItem({ position: [0, 0], value: 627.5, uncertainty: 50.2, synthetic: true, label: "sim-loop-010" }, { metric: "intensity", unit: "" });
    expect(d.title).toBe("sim-loop-010");
    expect(d.lines).toEqual(["Intensity: 628", "Uncertainty ± 50.2"]);
    expect(d.synthetic).toBe(true);
  });
  it("leaves out the uncertainty when the tool gave none", () => {
    const d = describeItem({ position: [0, 0], value: 4, uncertainty: 0 }, { metric: "count", unit: "" });
    expect(d.lines).toEqual(["Count: 4"]);
  });
  it("shows a plain site by name only", () => {
    const d = describeItem({ position: [0, 0], value: 1, uncertainty: 0, label: "Ospedale" }, { metric: "site", unit: "" });
    expect(d).toEqual({ title: "Ospedale", lines: [], synthetic: false });
  });
});
