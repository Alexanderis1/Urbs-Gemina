import { describe, expect, it } from "vitest";
import { columnPx, columnScale, isDense, MARKER, metersPerPixel, zoomStep } from "@/lib/markers";

describe("3D markers keep a readable size on screen at every zoom", () => {
  it("knows how many metres one pixel covers in Rome", () => {
    // MapLibre (512 px tiles): about 78 km per pixel at zoom 0 on the equator, halved at every zoom step.
    expect(metersPerPixel(0, 0)).toBeCloseTo(78271.5, 0);
    expect(metersPerPixel(12)).toBeCloseTo(metersPerPixel(13) * 2, 6);
    expect(metersPerPixel(15)).toBeGreaterThan(1.5);
    expect(metersPerPixel(15)).toBeLessThan(2.1);
  });

  it("makes columns taller in metres when the view is wide, and never shorter than the buildings when close", () => {
    expect(columnScale(12)).toBeCloseTo(metersPerPixel(12), 6);
    expect(columnScale(18)).toBe(MARKER.minScale);
    // A place marker at the closest zoom still rises above a typical Roman block (about 25 m).
    expect(columnPx(null) * columnScale(19)).toBeGreaterThan(40);
  });

  it("gives places one height and readings a height that follows the value", () => {
    expect(columnPx(null)).toBe(MARKER.sitePx);
    expect(columnPx(0)).toBe(MARKER.valueMinPx);
    expect(columnPx(1)).toBe(MARKER.valueMaxPx);
    expect(columnPx(0.5)).toBe((MARKER.valueMinPx + MARKER.valueMaxPx) / 2);
    expect(columnPx(7)).toBe(MARKER.valueMaxPx);
    expect(columnPx(-1)).toBe(MARKER.valueMinPx);
  });

  it("draws many markers slim and without badges", () => {
    expect(isDense(40)).toBe(false);
    expect(isDense(MARKER.denseFrom + 1)).toBe(true);
  });

  it("only reacts to zoom in quarter steps, so the map is not rebuilt on every frame", () => {
    expect(zoomStep(12.3)).toBe(12.25);
    expect(zoomStep(12.4)).toBe(12.5);
  });
});
