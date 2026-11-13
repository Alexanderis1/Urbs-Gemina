import { describe, expect, it } from "vitest";
import { areaToArg, areaLabel } from "@/lib/area";

describe("area argument", () => {
  it("encodes the whole city", () => {
    expect(areaToArg({ type: "city" })).toBe("city");
  });
  it("encodes a municipio and an urban zone by id", () => {
    expect(areaToArg({ type: "municipio", id: "1" })).toBe("municipio:1");
    expect(areaToArg({ type: "zone", id: "1a" })).toBe("zone:1A");
  });
  it("passes a drawn polygon as GeoJSON", () => {
    const poly = { type: "Polygon" as const, coordinates: [[[12.4, 41.9], [12.5, 41.9], [12.5, 42.0], [12.4, 41.9]]] };
    expect(areaToArg({ type: "polygon", geometry: poly })).toEqual(poly);
  });
  it("has a readable label", () => {
    expect(areaLabel({ type: "municipio", id: "1" })).toBe("Municipio I");
    expect(areaLabel({ type: "municipio", id: "15" })).toBe("Municipio XV");
  });
});
