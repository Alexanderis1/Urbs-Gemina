import { describe, expect, it } from "vitest";
import { buildScenarioChange } from "@/lib/scenario";

const site = { lon: "12.4823", lat: "41.8958", height_m: "25", band: "3500" };

describe("run_scenario change shapes (WS4)", () => {
  it("adds an antenna as a site object", () => {
    expect(buildScenarioChange("antenna", site)).toEqual({
      action: "add",
      site: { lon: 12.4823, lat: 41.8958, height_m: 25, band: "3500" },
    });
  });

  it("uses the same site for population exposure", () => {
    expect(buildScenarioChange("population_exposure", site)).toEqual({
      site: { lon: 12.4823, lat: 41.8958, height_m: 25, band: "3500" },
    });
  });

  it("closes a road by street name", () => {
    expect(buildScenarioChange("road_closure", { street: " Via del Corso " })).toEqual({ close: { street: "Via del Corso" } });
  });

  it("leaves out empty height", () => {
    expect(buildScenarioChange("antenna", { ...site, height_m: "" })).toEqual({
      action: "add",
      site: { lon: 12.4823, lat: 41.8958, band: "3500" },
    });
  });
});

describe("scenario catalogue", () => {
  it("offers eight tiles covering all nine engine kinds", async () => {
    const { SCENARIOS, resolveKind } = await import("@/lib/scenario");
    expect(SCENARIOS).toHaveLength(8);
    const kinds = new Set<string>();
    for (const s of SCENARIOS) {
      kinds.add(resolveKind(s.id, s.defaults));
      if (s.id === "road_closure") {
        kinds.add(resolveKind(s.id, { ...s.defaults, mode: "event" }));
        kinds.add(resolveKind(s.id, { ...s.defaults, mode: "roadworks" }));
      }
    }
    expect([...kinds].sort()).toEqual(
      ["antenna", "chemical_plume", "emergency_access", "heatwave", "population_exposure", "rain_flood", "river_flood", "road_closure", "traffic_event"].sort(),
    );
  });

  it("marks the network simulations as heavy", async () => {
    const { isHeavy } = await import("@/lib/scenario");
    expect(isHeavy("road_closure")).toBe(true);
    expect(isHeavy("traffic_event")).toBe(true);
    expect(isHeavy("emergency_access")).toBe(true);
    expect(isHeavy("river_flood")).toBe(false);
    expect(isHeavy("antenna")).toBe(false);
  });

  it("knows which kinds only run on a few blocks", async () => {
    const { needsSmallArea } = await import("@/lib/scenario");
    expect(needsSmallArea("road_closure")).toBe(true);
    expect(needsSmallArea("traffic_event")).toBe(true);
    // Emergency access runs on a whole municipio.
    expect(needsSmallArea("emergency_access")).toBe(false);
    expect(needsSmallArea("heatwave")).toBe(false);
  });
});

describe("change objects for the new kinds", () => {
  it("river flood: the 200-year flood scenario is the default", async () => {
    const { SCENARIOS } = await import("@/lib/scenario");
    const spec = SCENARIOS.find((x) => x.id === "river_flood")!;
    expect(buildScenarioChange("river_flood", { ...spec.defaults })).toEqual({ gauge: "tevere_ripetta", return_period_years: 200 });
    expect(buildScenarioChange("river_flood", { mode: "return", return_period: "500" })).toEqual({
      gauge: "tevere_ripetta",
      return_period_years: 500,
    });
  });

  it("river flood: rise, gauge level or forecast", () => {
    expect(buildScenarioChange("river_flood", { mode: "rise", rise_m: "3" })).toEqual({ rise_m: 3 });
    expect(buildScenarioChange("river_flood", { mode: "level", gauge: "tevere_ripetta", level_m: "14" })).toEqual({
      gauge: "tevere_ripetta",
      level_m: 14,
    });
    expect(buildScenarioChange("river_flood", { mode: "forecast", gauge: "tevere_ripetta" })).toEqual({
      gauge: "tevere_ripetta",
      forecast_day: "peak",
    });
  });

  it("rain flood: rain amount, radar or forecast, with an optional high river", () => {
    expect(buildScenarioChange("rain_flood", { mode: "rain", rain_mm: "60", duration_h: "1", river_rise_m: "" })).toEqual({
      rain_mm: 60,
      duration_h: 1,
    });
    expect(buildScenarioChange("rain_flood", { mode: "radar" })).toEqual({ source: "radar" });
    expect(buildScenarioChange("rain_flood", { mode: "forecast", river_rise_m: "3" })).toEqual({ source: "forecast", river: { rise_m: 3 } });
  });

  it("chemical release: named site or point, forecast or entered wind", () => {
    expect(
      buildScenarioChange("chemical_plume", { place: "site", site: " Papasped ", substance: "ammonia", release_kg_s: "5", wind: "forecast" }),
    ).toEqual({ site: "Papasped", substance: "ammonia", release_kg_s: 5, wind: "forecast" });
    expect(
      buildScenarioChange("chemical_plume", {
        place: "point",
        lon: "12.5",
        lat: "41.9",
        substance: "chlorine",
        release_kg_s: "2",
        wind: "manual",
        wind_speed_ms: "3",
        wind_from_deg: "270",
      }),
    ).toEqual({ lon: 12.5, lat: 41.9, substance: "chlorine", release_kg_s: 2, wind: { speed_ms: 3, from_deg: 270 } });
  });

  it("emergency access: service, closed street, optional river flood", () => {
    expect(buildScenarioChange("emergency_access", { service: "fire", street: " Via Ostiense ", flood_rise_m: "" })).toEqual({
      service: "fire",
      close: { street: "Via Ostiense" },
    });
    expect(buildScenarioChange("emergency_access", { service: "ambulance", street: "Via Ostiense", flood_rise_m: "3" })).toEqual({
      service: "ambulance",
      close: { street: "Via Ostiense" },
      flood: { kind: "river_flood", change: { rise_m: 3 } },
    });
  });

  it("heatwave: forecast or entered temperatures, optional trees and depaving", () => {
    expect(buildScenarioChange("heatwave", { temperature: "forecast", trees_pct: "", depave_pct: "" })).toEqual({ temperature: "forecast" });
    expect(buildScenarioChange("heatwave", { temperature: "manual", tmax_c: "36", tmin_c: "24", trees_pct: "10", depave_pct: "10" })).toEqual({
      tmax_c: 36,
      tmin_c: 24,
      plant_trees: { cover_added_pct: 10 },
      depave: { impervious_removed_pct: 10 },
    });
  });

  it("traffic event: public event or roadworks", () => {
    expect(buildScenarioChange("traffic_event", { mode: "event", street: "Viale Tiziano", attendees: "20000" })).toEqual({
      event: { street: "Viale Tiziano", attendees: 20000 },
    });
    expect(buildScenarioChange("traffic_event", { mode: "roadworks", street: "Via Nomentana", lanes_closed: "1" })).toEqual({
      roadworks: [{ street: "Via Nomentana", lanes_closed: 1 }],
    });
  });
});

describe("form checks", () => {
  it("asks for what is missing before a run", async () => {
    const { changeProblem } = await import("@/lib/scenario");
    expect(changeProblem("road_closure", { street: " " })).toMatch(/street/i);
    expect(changeProblem("river_flood", { mode: "rise", rise_m: "abc" })).toMatch(/number/i);
    expect(changeProblem("chemical_plume", { place: "point", lon: "", lat: "", substance: "ammonia", release_kg_s: "5", wind: "forecast" })).toMatch(
      /map|site/i,
    );
    expect(changeProblem("antenna", site)).toBeNull();
    expect(changeProblem("river_flood", { mode: "forecast", gauge: "tevere_ripetta" })).toBeNull();
  });
});

describe("scenario text in Italian", () => {
  it("speaks Italian", async () => {
    const { setLang } = await import("@/lib/i18n");
    const { changeProblem, scenarioSpec, groupLabel } = await import("@/lib/scenario");
    setLang("it");
    try {
      expect(changeProblem("road_closure", { street: " " })).toBe("Scrivi il nome della strada.");
      expect(changeProblem("river_flood", { mode: "rise", rise_m: "abc" })).toBe("Aumento del fiume: inserisci un numero.");
      expect(scenarioSpec("heatwave").label).toBe("Ondata di calore");
      expect(groupLabel("Water")).toBe("Acqua");
    } finally {
      setLang("en");
    }
    expect(scenarioSpec("heatwave").label).toBe("Heatwave");
  });
});
