import { describe, expect, it } from "vitest";
import { parseMapAction, parseMapActions, areaFromId } from "@/lib/mapActions";

describe("map actions (shared with the voice agent's client tools)", () => {
  it("accepts fly_to inside Rome", () => {
    expect(parseMapAction({ tool: "fly_to", args: { lon: 12.48, lat: 41.9, zoom: 15 } })).toEqual({
      tool: "fly_to",
      args: { lon: 12.48, lat: 41.9, zoom: 15 },
    });
  });

  it("drops points outside Rome", () => {
    expect(parseMapAction({ tool: "fly_to", args: { lon: 2.35, lat: 48.85 } })).toBeNull();
    expect(parseMapAction({ tool: "show_radius", args: { lon: 9.19, lat: 45.46, radius_m: 300 } })).toBeNull();
  });

  it("drops unknown tools and malformed args", () => {
    expect(parseMapAction({ tool: "delete_city", args: {} })).toBeNull();
    expect(parseMapAction({ tool: "fly_to", args: { lon: "12.4", lat: 41.9 } })).toBeNull();
    expect(parseMapAction({ tool: "show_layer", args: { layer: "rain" } })).toBeNull();
    expect(parseMapAction({ tool: "open_screen", args: { screen: "admin" } })).toBeNull();
    expect(parseMapAction("fly_to")).toBeNull();
  });

  it("keeps the valid entries of a list", () => {
    const list = [
      { tool: "show_layer", args: { layer: "rain", visible: true } },
      { tool: "fly_to", args: { lon: 0, lat: 0 } },
      { tool: "open_screen", args: { screen: "permit" } },
    ];
    expect(parseMapActions(list).map((a) => a.tool)).toEqual(["show_layer", "open_screen"]);
    expect(parseMapActions(undefined)).toEqual([]);
  });

  it("turns area ids into areas", () => {
    expect(areaFromId("city")).toEqual({ type: "city" });
    expect(areaFromId("municipio:I")).toEqual({ type: "municipio", id: "I" });
    expect(areaFromId("zone:1A")).toEqual({ type: "zone", id: "1A" });
    expect(areaFromId("nonsense")).toBeNull();
  });
});
