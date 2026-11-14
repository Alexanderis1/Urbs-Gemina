import { describe, expect, it } from "vitest";
import { boundsOf, circlePolygon, distanceM } from "@/lib/geo";

describe("circle polygon (the 300 m area sent to tools)", () => {
  it("has 64 vertices plus the closing point, all at the radius", () => {
    const p = circlePolygon(12.4823, 41.8959, 300);
    const ring = p.coordinates[0]!;
    expect(p.type).toBe("Polygon");
    expect(ring).toHaveLength(65);
    expect(ring[0]).toEqual(ring[64]);
    for (const [lon, lat] of ring) expect(Math.abs(distanceM(12.4823, 41.8959, lon!, lat!) - 300)).toBeLessThan(1.5);
  });
});

describe("bounds of result shapes (camera fit only)", () => {
  it("covers every coordinate of nested geometries", () => {
    const a = { type: "Polygon", coordinates: [[[12.4, 41.8], [12.5, 41.8], [12.5, 41.9], [12.4, 41.8]]] };
    const b = { type: "MultiPolygon", coordinates: [[[[12.6, 41.95], [12.61, 41.96], [12.6, 41.95]]]] };
    expect(boundsOf([a, b])).toEqual([[12.4, 41.8], [12.61, 41.96]]);
  });
  it("returns null when there is nothing to fit", () => {
    expect(boundsOf([])).toBeNull();
    expect(boundsOf([{ type: "Polygon", coordinates: [] }])).toBeNull();
  });
});
