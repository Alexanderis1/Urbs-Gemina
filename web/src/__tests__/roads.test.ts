import { describe, expect, it } from "vitest";
import { cellToLatLng, gridDisk, latLngToCell } from "h3-js";
import { trafficColor } from "@/lib/colors";
import type { HeatCell } from "@/lib/here";
import { certainty, fieldOnCells, roadPieces, roadWidthPx, type RoadNet } from "@/lib/roads";

/** A patch of the city grid around a point: the centre cell scores `mid`, its ring `ring`. */
function patch(lat: number, lon: number, mid: number, ring: number): HeatCell[] {
  const centre = latLngToCell(lat, lon, 8);
  return gridDisk(centre, 1).map((h3) => {
    const [la, lo] = cellToLatLng(h3);
    return { h3, lon: lo, lat: la, value: h3 === centre ? mid : ring };
  });
}

describe("the value of a layer along the streets", () => {
  const cells = patch(41.9, 12.48, 1, 0);
  const centre = cells.find((c) => c.value === 1)!;
  const at = fieldOnCells(cells, (c) => c.value);

  it("is the cell's own value at its centre and blends towards the neighbours in between", () => {
    const mid = at(centre.lon, centre.lat)!;
    expect(mid.t).toBeGreaterThan(0.9);
    expect(mid.cell.h3).toBe(centre.h3);
    const other = cells.find((c) => c.value === 0)!;
    const between = at((centre.lon + other.lon) / 2, (centre.lat + other.lat) / 2)!;
    expect(between.t).toBeGreaterThan(0.1);
    expect(between.t).toBeLessThan(0.9);
  });

  it("carries how sure each place is, blended like the value", () => {
    const sure = fieldOnCells(cells, (c) => c.value, (c) => (c.value === 1 ? 1 : 0));
    expect(sure(centre.lon, centre.lat)!.a).toBeGreaterThan(0.9);
    const other = cells.find((c) => c.value === 0)!;
    expect(sure(other.lon, other.lat)!.a).toBeLessThan(0.1);
    // Without a rule every place counts as sure.
    expect(at(other.lon, other.lat)!.a).toBe(1);
  });

  it("knows a model-only estimate from a measured one by the width of its range", () => {
    expect(certainty({ lon: 0, lat: 0, value: 30, low: 20, high: 42 })).toBe(1);
    expect(certainty({ lon: 0, lat: 0, value: 28, low: 5, high: 45 })).toBe(0);
    const mid = certainty({ lon: 0, lat: 0, value: 30, low: 15, high: 45 });
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(1);
    expect(certainty({ lon: 0, lat: 0, value: 30 })).toBe(1);
  });

  it("says nothing where the layer has no cells", () => {
    expect(at(12.9, 42.3)).toBeNull();
    expect(fieldOnCells([{ lon: 12.48, lat: 41.9, value: 1 }], (c) => c.value)(12.48, 41.9)).toBeNull();
  });

  it("cuts a street into short pieces that follow each other, each with its own value", () => {
    // One straight street across the patch, west to east; the ends outside the patch are left out.
    const net: RoadNet = { classes: ["primary"], roads: [[0, [centre.lon - 0.01, centre.lat, centre.lon + 0.01, centre.lat]]] };
    const pieces = roadPieces(net, at, 120);
    expect(pieces.length).toBeGreaterThan(10);
    for (let i = 1; i < pieces.length; i++) expect(pieces[i]!.path[0]).toEqual(pieces[i - 1]!.path.at(-1));
    expect(pieces.every((p) => p.cls === "primary" && p.a === 1)).toBe(true);
    // A gradient: the value rises towards the centre cell and falls again, in small steps.
    const ts = pieces.map((p) => p.t);
    expect(Math.max(...ts)).toBeGreaterThan(0.8);
    expect(ts[0]!).toBeLessThan(0.3);
    const steps = ts.slice(1).map((t, i) => Math.abs(t - ts[i]!));
    expect(Math.max(...steps)).toBeLessThan(0.25);
  });

  it("leaves out the stretches of street outside the layer", () => {
    const net: RoadNet = { classes: ["motorway"], roads: [[0, [12.9, 42.3, 12.91, 42.3]]] };
    expect(roadPieces(net, at, 120)).toEqual([]);
  });

  it("draws big roads wider than small ones, and all of them wider when zoomed in", () => {
    expect(roadWidthPx("motorway", 11)).toBeGreaterThan(roadWidthPx("tertiary", 11));
    expect(roadWidthPx("primary", 14)).toBeGreaterThan(roadWidthPx("primary", 10));
    expect(roadWidthPx("unknown", 11)).toBeGreaterThan(0);
  });

  it("colours traffic like navigation maps: green when flowing, dark red when blocked", () => {
    const [r0, g0] = trafficColor(0);
    const [r1, g1] = trafficColor(1);
    expect(g0).toBeGreaterThan(r0);
    expect(r1).toBeGreaterThan(g1 * 3);
  });
});
