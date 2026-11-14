import { describe, expect, it } from "vitest";
import { fmtNumber, keyFigures, rangeText, humanise, isQuantile, labelFor, summariseScenario } from "@/lib/scenarioResult";

const square = { type: "MultiPolygon", coordinates: [[[[12.47, 41.89], [12.48, 41.89], [12.48, 41.9], [12.47, 41.89]]]] };

describe("scenario result labels", () => {
  it("humanises unknown keys", () => {
    expect(humanise("residents_cut_off")).toBe("Residents cut off");
    expect(labelFor("residents_cut_off")).toBe("Residents cut off");
  });

  it("uses the dictionary for known keys and paths", () => {
    expect(labelFor("discharge_m3s")).toMatch(/discharge/i);
    expect(labelFor("what_if.cooling_day_c")).toMatch(/cooling/i);
  });

  it("detects quantile objects", () => {
    expect(isQuantile({ p5: 1, p50: 2, p95: 3 })).toBe(true);
    expect(isQuantile({ p5: 1, p50: "2", p95: 3 })).toBe(false);
    expect(isQuantile(null)).toBe(false);
  });
});

describe("summariseScenario", () => {
  const river = {
    kind: "river_flood",
    metric: "flooded area",
    unit: "km²",
    model: "height_above_nearest_river",
    calibration: "uncalibrated",
    rise_m: 3,
    gauge_level_m: 9.2,
    discharge_m3s: 1450,
    alert_probability: { ordinary: 0.6, high: 0.1 },
    flooded_km2: { p5: 0.4, p50: 0.9, p95: 1.6 },
    footprint_p50: square,
    footprint_p95: square,
    residents: {
      p5: { residents: 100, children: 10, sections_touched: 3 },
      p50: { residents: 300, children: 30, sections_touched: 6 },
      p95: { residents: 900, children: 70, sections_touched: 12 },
    },
    sensitive_sites: {
      count: 12,
      by_category: { school: 8, health: 4 },
      sites: Array.from({ length: 12 }, (_, i) => ({ name: `Site ${i}`, category: "school", lon: 12.47, lat: 41.89, probability: 0.5 })),
    },
  };
  const s = summariseScenario(river);

  it("keeps quantiles as ranges, including transposed resident counts", () => {
    const flooded = s.quantiles.find((q) => q.path === "flooded_km2");
    expect(flooded?.value).toEqual({ p5: 0.4, p50: 0.9, p95: 1.6 });
    expect(flooded?.unit).toBe("km²");
    const res = s.quantiles.find((q) => q.path === "residents.residents");
    expect(res?.value).toEqual({ p5: 100, p50: 300, p95: 900 });
  });

  it("collects footprints with their level and never lists them as facts", () => {
    expect(s.footprints.map((f) => [f.path, f.level])).toEqual([
      ["footprint_p50", "likely"],
      ["footprint_p95", "possible"],
    ]);
    expect(JSON.stringify(s.facts)).not.toMatch(/MultiPolygon/);
  });

  it("turns lists of rows into tables, capped, with the total", () => {
    const t = s.tables.find((x) => x.path === "sensitive_sites.sites");
    expect(t?.label).toBe("Sensitive sites");
    expect(t?.total).toBe(12);
    expect(t?.rows).toHaveLength(8);
    expect(t?.columns).not.toContain("lon");
    expect(t?.columns).toContain("Name");
  });

  it("collects places with coordinates from tables for the map", () => {
    expect(s.points.length).toBe(12);
    expect(s.points[0]).toMatchObject({ lon: 12.47, lat: 41.89 });
  });

  it("lists scalars as facts with units and leaves out the headline fields", () => {
    const rise = s.facts.find((f) => f.path === "rise_m");
    expect(rise?.value).toBe("3 m");
    expect(s.facts.find((f) => f.path === "discharge_m3s")?.value).toBe("1,450 m³/s");
    expect(s.facts.find((f) => f.path === "alert_probability")?.value).toMatch(/Ordinary 60%/);
    expect(s.facts.some((f) => ["kind", "metric", "unit"].includes(f.path))).toBe(false);
  });

  it("returns the baseline and variant pair when present", () => {
    const pair = summariseScenario({ baseline: { p5: 1, p50: 2, p95: 3 }, variant: { p5: 2, p50: 3, p95: 4 }, unit: "people" });
    expect(pair.compare?.baseline.p50).toBe(2);
    expect(pair.compare?.variant.p50).toBe(3);
    expect(pair.quantiles).toHaveLength(0);
  });

  it("lifts a nested baseline / variant pair into the comparison", () => {
    const ea = summariseScenario({
      residents_cut_off: 3061,
      residents_beyond_target: { baseline: { p5: 2539, p50: 2539, p95: 2539 }, variant: { p5: 3061, p50: 3061, p95: 3061 } },
      area: { area_km2: 19.984, id: "municipio:1" },
    });
    expect(ea.compare?.label).toBe("Residents beyond the target time");
    expect(ea.compare?.variant.p50).toBe(3061);
    expect(ea.quantiles.some((q) => q.path.startsWith("residents_beyond_target"))).toBe(false);
    expect(ea.facts.find((f) => f.path === "area")?.label).toBe("Operating area");
  });

  it("turns an object of like rows (official hazard classes) into a table, flattening one level", () => {
    const r = summariseScenario({
      official_hazard: {
        P1: { km2: 1.454, residents: { children_0_14: 38, residents: 402, sections_touched: 100 } },
        P2: { km2: 0.748, residents: { children_0_14: 0, residents: 4, sections_touched: 81 } },
      },
    });
    const t = r.tables.find((x) => x.path === "official_hazard");
    expect(t?.columns).toEqual(["", "Area (km²)", "Residents · Children (0-14)", "Residents", "Residents · Census sections touched"]);
    expect(t?.rows[0]).toEqual(["P1", "1.454", "38", "402", "100"]);
    expect(r.facts).toHaveLength(0);
  });

  it("puts names first and residents before sub-groups, whatever the key order", () => {
    const r = summariseScenario({
      hot_day: { children_0_14: { p5: 1, p50: 2, p95: 3 }, residents: { p5: 10, p50: 20, p95: 30 } },
      sections: [{ impervious_pct: 70, residents: 800, sez_id: "58091" }],
    });
    expect(r.quantiles.map((q) => q.path)).toEqual(["hot_day.residents", "hot_day.children_0_14"]);
    expect(r.tables[0]?.columns.slice(0, 2)).toEqual(["Section", "Residents"]);
  });

  it("reads the unit through _mean and _p50 endings", () => {
    expect(summariseScenario({ rain_mm_mean: 60 }).facts[0]?.value).toBe("60 mm");
  });

  it("keeps four significant figures for display", () => {
    expect(summariseScenario({ area: { area_km2: 19.984 } }).facts[0]?.value).toMatch(/19.98 km²/);
  });

  it("reports a not-available status with its reason", () => {
    const na = summariseScenario({ status: "not_available", reason: "No river cells inside this area." });
    expect(na.notAvailable).toBe("No river cells inside this area.");
  });

  it("reads nested zones of a chemical release", () => {
    const plume = summariseScenario({
      substance: "ammonia",
      zones: { aegl_2: { threshold_mg_m3: 110, max_distance_m: { p5: 200, p50: 400, p95: 900 }, footprint_possible: square } },
    });
    expect(plume.footprints[0]).toMatchObject({ path: "zones.aegl_2.footprint_possible", level: "possible" });
    expect(plume.quantiles[0]?.unit).toBe("m");
    expect(plume.facts.find((f) => f.path === "substance")?.value).toBe("ammonia");
  });
});

describe("sample results", () => {
  it("give every new kind something to show", async () => {
    const { mockTool } = await import("@/api/mock");
    for (const kind of ["river_flood", "rain_flood", "heatwave", "chemical_plume", "emergency_access", "traffic_event"]) {
      const env = await mockTool("run_scenario", { kind, area: "municipio:1", change: {} });
      const s = summariseScenario(env.result);
      expect(s.compare !== null || s.quantiles.length > 0, kind).toBe(true);
    }
    const river = summariseScenario((await mockTool("run_scenario", { kind: "river_flood", area: "municipio:1", change: { rise_m: 3 } })).result);
    expect(river.footprints.map((f) => f.level)).toEqual(["likely", "possible"]);
  });

  it("groups thousands so large counts are easy to read, and keeps small values precise", () => {
    expect(fmtNumber(162584)).toBe("162,584");
    expect(fmtNumber(19.984)).toBe("19.98");
    expect(fmtNumber(0.246)).toBe("0.246");
  });

  it("says so plainly when a range has no spread, instead of repeating the same number", () => {
    expect(rangeText({ p5: 7.7, p50: 16.5, p95: 34.6 })).toBe("range 7.7 to 34.6");
    expect(rangeText({ p5: 16784, p50: 16784, p95: 16784 })).toBe("same in every model run");
  });

  // Shape of a real rain_flood run on the live service (14 Nov 2026), cut down.
  const rain = {
    area: { area_km2: 19.984, id: "municipio:1" },
    flooded_km2_p50: 0.604,
    hotspots_count: 334,
    residents: { p50: { children_0_14: 414, residents: 4176, sections_touched: 383 } },
    sensitive_sites: { count: 30, by_category: { education: 4, health: 3 } },
    sewer: { efficiency: { p5: 0.143, p50: 0.259, p95: 0.429 }, outfalls_considered: 28 },
    total_depth_index: { p5: 240.6, p50: 686.1, p95: 1383.4 },
  };

  it("puts people and extent first in the key figures, not model internals", () => {
    const figures = keyFigures(summariseScenario(rain));
    expect(figures.map((f) => f.path)).toEqual(["residents.p50.residents", "residents.p50.children_0_14", "flooded_km2_p50", "hotspots_count"]);
    expect(figures[0]).toMatchObject({ value: "4,176", note: "middle estimate (P50)" });
    expect(figures[2]).toMatchObject({ value: "0.604", unit: "km²" });
    // The operating area's own size is not a result.
    expect(figures.some((f) => f.path.startsWith("area"))).toBe(false);
  });

  it("keeps the range on key figures that have one, and falls back to the first ranges when nothing is ranked", () => {
    const heat = summariseScenario({ hot_day: { residents: { p5: 100, p50: 150, p95: 220 } }, sewer: { efficiency: { p5: 0.1, p50: 0.2, p95: 0.3 } } });
    expect(keyFigures(heat)[0]).toMatchObject({ path: "hot_day.residents", value: "150", note: "range 100 to 220" });
    const other = summariseScenario({ sewer: { efficiency: { p5: 0.1, p50: 0.2, p95: 0.3 } } });
    expect(keyFigures(other).map((f) => f.path)).toEqual(["sewer.efficiency"]);
  });
});
