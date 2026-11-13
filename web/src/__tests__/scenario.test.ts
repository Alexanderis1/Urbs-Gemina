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
