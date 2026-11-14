import { describe, expect, it } from "vitest";
import { availableMetrics, describeItem, dotRadiusPx, formatValue, metricInfo, normalizeLayer, pointStyle, showValueLabels, valueExtent } from "@/lib/layers";

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
    expect(d.lines).toEqual(["Traffic flow: 628", "Uncertainty ± 50.2"]);
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

describe("metricInfo", () => {
  it("gives the plain name and unit of the values the tool returns", () => {
    expect(metricInfo("pm10")).toMatchObject({ label: "PM10", unit: "µg/m³" });
    expect(metricInfo("no2")).toMatchObject({ label: "NO₂", unit: "µg/m³" });
    expect(metricInfo("electricField")).toMatchObject({ label: "Electric field", unit: "V/m" });
    expect(metricInfo("intensity")).toMatchObject({ label: "Traffic flow", unit: "vehicles/h" });
    expect(metricInfo("availableVehicles")).toMatchObject({ label: "Vehicles available", unit: "", each: "vehicle" });
  });

  it("falls back to readable words and no unit for a value it does not know", () => {
    expect(metricInfo("roadSurface_temp")).toEqual({ label: "Road surface temp", unit: "" });
  });
});

describe("points over the 3D city", () => {
  const obs = (values: number[], key = "no2") => ({
    type: "observations",
    observations: values.map((v, i) => ({ id: `urn:x:s${i}`, lon: 12.4 + i / 100, lat: 41.9, values: { [key]: v }, sigma: { [key]: 1 } })),
  });

  it("an observation layer carries its unit", () => {
    expect(normalizeLayer(obs([7, 38])).unit).toBe("µg/m³");
    expect(normalizeLayer(obs([7, 38], "pm25")).metric).toBe("pm25");
  });

  it("colours by value only when the values differ", () => {
    expect(pointStyle(normalizeLayer(obs([7, 38])))).toBe("values");
    // Every scooter is one vehicle: a colour scale from 1 to 1 would say nothing.
    expect(pointStyle(normalizeLayer(obs([1, 1, 1], "availableVehicles")))).toBe("sites");
    expect(pointStyle({ metric: "site", items: [] })).toBe("sites");
    expect(pointStyle({ metric: "count", items: [{ value: 2, uncertainty: 0 }] })).toBe("sized");
  });

  it("writes the value next to each dot only when there are few of them", () => {
    expect(showValueLabels(normalizeLayer(obs([7, 38, 12])))).toBe(true);
    expect(showValueLabels(normalizeLayer(obs(Array.from({ length: 80 }, (_, i) => i))))).toBe(false);
    expect(showValueLabels(normalizeLayer(obs([1, 1], "availableVehicles")))).toBe(false);
  });

  it("draws a few dots large and many dots small", () => {
    expect(dotRadiusPx(10)).toBeGreaterThan(dotRadiusPx(500));
    expect(dotRadiusPx(500)).toBeGreaterThan(dotRadiusPx(5000));
    expect(dotRadiusPx(5000)).toBeGreaterThanOrEqual(4);
  });

  it("names the value in the hover text", () => {
    const d = normalizeLayer(obs([38]));
    expect(describeItem(d.items[0]!, d).lines[0]).toBe("NO₂: 38 µg/m³");
  });
});

describe("several values per sensor", () => {
  const result = {
    type: "observations",
    observations: [
      { id: "a", lon: 12.4, lat: 41.9, values: { no2: 6.2, pm10: 5.6, pm25: 3.6 }, sigma: { no2: 3.1, pm10: 2.8, pm25: 1.8 } },
      { id: "b", lon: 12.5, lat: 41.9, values: { no2: 9, pm10: 12.2, pm25: 4 }, sigma: { no2: 3, pm10: 2, pm25: 1 } },
    ],
  };

  it("lists every value the sensors report, the usual one first", () => {
    expect(availableMetrics(result)).toEqual(["pm10", "pm25", "no2"]);
    expect(availableMetrics({ type: "features" })).toEqual([]);
    // Flags for the tools are not readings.
    expect(availableMetrics({ type: "observations", observations: [{ values: { electricField: 0.2, at_cap: 0 } }] })).toEqual(["electricField"]);
  });

  it("shows the value the operator picked, or the usual one", () => {
    expect(normalizeLayer(result).metric).toBe("pm10");
    const picked = normalizeLayer(result, "no2");
    expect(picked.metric).toBe("no2");
    expect(picked.items.map((i) => i.value)).toEqual([6.2, 9]);
    expect(picked.items[0]!.uncertainty).toBe(3.1);
    // A value the layer does not have is ignored.
    expect(normalizeLayer(result, "intensity").metric).toBe("pm10");
  });
});
