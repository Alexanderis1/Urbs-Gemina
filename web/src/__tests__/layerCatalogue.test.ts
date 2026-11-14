import { describe, expect, it } from "vitest";
import { MAP_LAYERS, PUBLIC_LAYERS, isFused, layerLabel, layersFor } from "@/lib/layerCatalogue";

describe("map layer catalogue", () => {
  it("lists each layer once", () => {
    for (const list of [MAP_LAYERS, PUBLIC_LAYERS]) expect(new Set(list.map((l) => l.id)).size).toBe(list.length);
  });

  it("knows which layers are the twin's own estimates per cell", () => {
    expect(isFused("air_no2")).toBe(true);
    expect(isFused("hospitals")).toBe(false);
    expect(isFused(null)).toBe(false);
  });

  it("residents see a short list in plain words, taken from the layers staff have", () => {
    expect(PUBLIC_LAYERS.length).toBeLessThan(MAP_LAYERS.length);
    const staffIds = new Set(MAP_LAYERS.map((l) => l.id));
    for (const l of PUBLIC_LAYERS) expect(staffIds.has(l.id)).toBe(true);
    // Raw model points and simulated traffic loops are operator material, not public information.
    expect(PUBLIC_LAYERS.map((l) => l.id)).not.toContain("emf_baseline");
    expect(PUBLIC_LAYERS.map((l) => l.id)).not.toContain("traffic_flow");
    expect(PUBLIC_LAYERS.every((l) => !/[_]/.test(l.label))).toBe(true);
  });

  it("names a layer for the experience that shows it", () => {
    expect(layersFor("staff")).toBe(MAP_LAYERS);
    expect(layersFor("public")).toBe(PUBLIC_LAYERS);
    expect(layerLabel("air_pm25", "staff")).toBe("Air: PM2.5");
    expect(layerLabel("air_pm25", "public")).toBe("Air: fine dust (PM2.5)");
    expect(layerLabel(null, "public")).toBe("Buildings only");
    expect(layerLabel("something_new", "public")).toBe("Something new");
  });
});

describe("map layer catalogue in Italian", () => {
  it("speaks Italian", async () => {
    const { setLang } = await import("@/lib/i18n");
    const { GROUPS } = await import("@/lib/layerCatalogue");
    setLang("it");
    try {
      expect(layerLabel("air_pm25", "public")).toBe("Aria: polveri sottili (PM2.5)");
      expect(layerLabel("rain", "public")).toBe("Pioggia adesso");
      expect(layerLabel(null, "public")).toBe("Solo edifici");
      expect(layersFor("public").find((l) => l.id === "antenna_register")?.label).toBe("Antenne di telefonia");
      expect(GROUPS[0]!.label).toBe("Stime live (fusione di sensori)");
    } finally {
      setLang("en");
    }
  });
});
