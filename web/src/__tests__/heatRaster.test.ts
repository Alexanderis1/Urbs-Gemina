import { describe, expect, it } from "vitest";
import { cellToLatLng, gridDisk, latLngToCell } from "h3-js";
import { heatRaster, type HeatPoint } from "@/lib/heatRaster";

const ramp = (t: number): [number, number, number] => [Math.round(255 * t), 0, 0];

/** A patch of the city grid: the centre cell scores 1, its six neighbours 0. */
function patch(): HeatPoint<string>[] {
  const centre = latLngToCell(41.9, 12.48, 8);
  return gridDisk(centre, 1).map((h3) => {
    const [lat, lon] = cellToLatLng(h3);
    return { lon, lat, t: h3 === centre ? 1 : 0, data: h3 };
  });
}

describe("a smooth heatmap instead of tiles", () => {
  const points = patch();
  const centre = points.find((p) => p.t === 1)!;
  const other = points.find((p) => p.t === 0)!;
  const r = heatRaster(points, { ramp, spacingM: 800 });

  const pixel = (lon: number, lat: number) => {
    const [w, s, e, n] = r.bounds;
    const x = Math.floor(((lon - w) / (e - w)) * r.width);
    const y = Math.floor(((n - lat) / (n - s)) * r.height);
    const i = (y * r.width + x) * 4;
    return { red: r.pixels[i]!, alpha: r.pixels[i + 3]! };
  };

  it("covers the data with a small margin and stays a reasonable size", () => {
    const [w, s, e, n] = r.bounds;
    for (const p of points) {
      expect(p.lon).toBeGreaterThan(w);
      expect(p.lon).toBeLessThan(e);
      expect(p.lat).toBeGreaterThan(s);
      expect(p.lat).toBeLessThan(n);
    }
    expect(r.width).toBeLessThanOrEqual(1024);
    expect(r.height).toBeLessThanOrEqual(1024);
    expect(r.pixels.length).toBe(r.width * r.height * 4);
  });

  it("is the value of the place at its centre and changes gradually in between, with no edges", () => {
    expect(pixel(centre.lon, centre.lat).red).toBeGreaterThan(160);
    const mid = pixel((centre.lon + other.lon) / 2, (centre.lat + other.lat) / 2).red;
    expect(mid).toBeGreaterThan(40);
    expect(mid).toBeLessThan(200);
    expect(pixel(other.lon, other.lat).red).toBeLessThan(mid);
  });

  it("fades out softly where there is no data", () => {
    const [w, , , n] = r.bounds;
    expect(pixel(w + 1e-6, n - 1e-6).alpha).toBe(0);
    expect(pixel(centre.lon, centre.lat).alpha).toBeGreaterThan(100);
  });

  it("makes the less certain places more see-through", () => {
    const sure = heatRaster(points.map((p) => ({ ...p, a: 1 })), { ramp, spacingM: 800 });
    const unsure = heatRaster(points.map((p) => ({ ...p, a: 0.3 })), { ramp, spacingM: 800 });
    const at = (x: typeof sure) => {
      const [w, s, e, n] = x.bounds;
      const px = Math.floor(((centre.lon - w) / (e - w)) * x.width);
      const py = Math.floor(((n - centre.lat) / (n - s)) * x.height);
      return x.pixels[(py * x.width + px) * 4 + 3]!;
    };
    expect(at(unsure)).toBeLessThan(at(sure));
  });

  it("tells which place a point of the map belongs to, for the card under the pointer", () => {
    expect(r.nearest(centre.lon + 0.0005, centre.lat)?.data).toBe(centre.data);
    expect(r.nearest(13.5, 43)).toBeNull();
  });

  it("draws nothing without data", () => {
    const empty = heatRaster([], { ramp, spacingM: 800 });
    expect(empty.width * empty.height).toBe(0);
    expect(empty.nearest(12.48, 41.9)).toBeNull();
  });
});
