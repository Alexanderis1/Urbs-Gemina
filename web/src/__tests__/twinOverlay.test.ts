import { describe, expect, it } from "vitest";
import { buildingAnchor, labelAnchor, OVER_TWIN, TWIN_MIN_ZOOM, TWIN_START_ZOOM, twinVisible } from "@/lib/twinOverlay";

const base = [
  { id: "background", type: "background" },
  { id: "water", type: "fill" },
  { id: "road", type: "line" },
  { id: "road-name", type: "symbol" },
  { id: "place-name", type: "symbol" },
];

describe("drawing order over the 3D city", () => {
  it("puts data just under the first name on the map, so street and place names stay readable", () => {
    expect(labelAnchor(base)).toBe("road-name");
    expect(labelAnchor([{ id: "background", type: "background" }])).toBeUndefined();
  });

  it("puts the buildings under the data when data is already on the map", () => {
    const withData = [...base.slice(0, 3), { id: "belief", type: "custom" }, ...base.slice(3)];
    expect(buildingAnchor(withData)).toBe("belief");
  });

  it("puts the buildings under the names when there is no data yet", () => {
    expect(buildingAnchor(base)).toBe("road-name");
    expect(buildingAnchor([{ id: "background", type: "background" }])).toBeUndefined();
  });

  it("draws data over the buildings without hiding it behind them", () => {
    expect(OVER_TWIN).toEqual({ depthCompare: "always", depthWriteEnabled: false });
  });
});

describe("3D city visibility", () => {
  it("screens start at a zoom where the buildings are drawn", () => {
    expect(TWIN_START_ZOOM).toBeGreaterThan(TWIN_MIN_ZOOM);
    expect(twinVisible(TWIN_START_ZOOM)).toBe(true);
    expect(twinVisible(TWIN_MIN_ZOOM)).toBe(true);
    expect(twinVisible(11.5)).toBe(false);
  });
});
