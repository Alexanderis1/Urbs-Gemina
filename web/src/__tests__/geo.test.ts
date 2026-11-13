import { describe, expect, it } from "vitest";
import { circlePolygon, distanceM } from "@/lib/geo";

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
