// A smooth heatmap instead of tiles (Alessandro, 14 Nov 2026: "no hexagons, a normal heatmap"). The twin's
// cells become one picture: every pixel takes the values of the cells around it, weighted by a soft bell
// of distance, so colours flow from place to place and fade out at the edge of the data. It is the value
// field, not a density: a crowded area is not hotter because it has more cells.
// Pure; drawn with a deck.gl BitmapLayer (src/map/heatLayer.ts). Reasoning: docs/design-system.md, decision 34.

export interface HeatPoint<T = unknown> {
  lon: number;
  lat: number;
  /** 0..1 on the colour scale. */
  t: number;
  /** 0..1 opacity factor (certainty); 1 when left out. */
  a?: number;
  data: T;
}

export interface HeatRaster<T = unknown> {
  /** RGBA, row by row from the north-west corner. */
  pixels: Uint8ClampedArray;
  width: number;
  height: number;
  /** [west, south, east, north] */
  bounds: [number, number, number, number];
  /** The place a point of the map belongs to (within about one cell), for the card under the pointer. */
  nearest: (lon: number, lat: number) => HeatPoint<T> | null;
}

export interface RasterOptions {
  ramp: (t: number) => [number, number, number];
  /** Distance between neighbouring cells, in metres. */
  spacingM: number;
  /** Opacity of a fully certain place, 0..255. */
  alpha?: number;
  /** Longest side of the picture in pixels. Basis: sharp enough at city zoom; the GPU blends it smoothly when zoomed in. */
  maxSide?: number;
}

const M_PER_DEG = 111_320;
/** Pixels per cell. Basis: four pixels across a cell give gradients without visible steps once smoothed by the GPU. */
const PX_PER_CELL = 4;

export function heatRaster<T>(points: HeatPoint<T>[], opts: RasterOptions): HeatRaster<T> {
  const none: HeatRaster<T> = { pixels: new Uint8ClampedArray(0), width: 0, height: 0, bounds: [0, 0, 0, 0], nearest: () => null };
  if (!points.length) return none;
  const alphaMax = opts.alpha ?? 170;
  const maxSide = opts.maxSide ?? 1024;
  const lat0 = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const mLon = M_PER_DEG * Math.cos((lat0 * Math.PI) / 180);
  const spacing = Math.max(20, opts.spacingM);
  // The bell: under half a cell wide, so neighbours blend into each other but a single high cell keeps its peak.
  const sigma = spacing * 0.45;
  const reach = sigma * 3;
  // Margin so the data fades out inside the picture instead of being cut.
  const marginLon = reach / mLon;
  const marginLat = reach / M_PER_DEG;
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  for (const p of points) {
    w = Math.min(w, p.lon);
    e = Math.max(e, p.lon);
    s = Math.min(s, p.lat);
    n = Math.max(n, p.lat);
  }
  w -= marginLon;
  e += marginLon;
  s -= marginLat;
  n += marginLat;
  const widthM = (e - w) * mLon;
  const heightM = (n - s) * M_PER_DEG;
  const pxM = Math.max(spacing / PX_PER_CELL, Math.max(widthM, heightM) / maxSide);
  const width = Math.max(1, Math.round(widthM / pxM));
  const height = Math.max(1, Math.round(heightM / pxM));

  // Places in buckets one reach wide: a pixel only looks at the buckets around it.
  const bucketM = reach;
  const buckets = new Map<string, HeatPoint<T>[]>();
  const key = (bx: number, by: number) => `${bx},${by}`;
  const bucketOf = (lon: number, lat: number): [number, number] => [Math.floor(((lon - w) * mLon) / bucketM), Math.floor(((lat - s) * M_PER_DEG) / bucketM)];
  for (const p of points) {
    const k = key(...bucketOf(p.lon, p.lat));
    const list = buckets.get(k);
    if (list) list.push(p);
    else buckets.set(k, [p]);
  }
  const around = (lon: number, lat: number): HeatPoint<T>[] => {
    const [bx, by] = bucketOf(lon, lat);
    const out: HeatPoint<T>[] = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) out.push(...(buckets.get(key(bx + dx, by + dy)) ?? []));
    return out;
  };

  // Colours computed once for 256 steps of the scale.
  const lut = new Uint8ClampedArray(256 * 3);
  for (let i = 0; i < 256; i++) lut.set(opts.ramp(i / 255), i * 3);

  const pixels = new Uint8ClampedArray(width * height * 4);
  const inv2s2 = 1 / (2 * sigma * sigma);
  // Total weight at which a place counts as fully covered: about one cell right under the pixel.
  const full = 0.55;
  for (let y = 0; y < height; y++) {
    const lat = n - ((y + 0.5) / height) * (n - s);
    for (let x = 0; x < width; x++) {
      const lon = w + ((x + 0.5) / width) * (e - w);
      const near = around(lon, lat);
      if (!near.length) continue;
      let sw = 0;
      let st = 0;
      let sa = 0;
      for (const p of near) {
        const dx = (p.lon - lon) * mLon;
        const dy = (p.lat - lat) * M_PER_DEG;
        const d2 = dx * dx + dy * dy;
        if (d2 > reach * reach) continue;
        const k = Math.exp(-d2 * inv2s2);
        sw += k;
        st += k * p.t;
        sa += k * (p.a ?? 1);
      }
      if (sw < 1e-4) continue;
      const t = st / sw;
      const certainty = sa / sw;
      const cover = Math.min(1, sw / full);
      // Smooth step at the edge of the data, so it fades instead of ending in a line.
      const edge = cover * cover * (3 - 2 * cover);
      const c = Math.max(0, Math.min(255, Math.round(t * 255))) * 3;
      const i = (y * width + x) * 4;
      pixels[i] = lut[c]!;
      pixels[i + 1] = lut[c + 1]!;
      pixels[i + 2] = lut[c + 2]!;
      pixels[i + 3] = Math.round(alphaMax * edge * certainty);
    }
  }

  const nearest = (lon: number, lat: number): HeatPoint<T> | null => {
    if (lon < w || lon > e || lat < s || lat > n) return null;
    let best: HeatPoint<T> | null = null;
    let bestD = (spacing * 0.75) ** 2;
    for (const p of around(lon, lat)) {
      const dx = (p.lon - lon) * mLon;
      const dy = (p.lat - lat) * M_PER_DEG;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD) {
        bestD = d2;
        best = p;
      }
    }
    return best;
  };

  return { pixels, width, height, bounds: [w, s, e, n], nearest };
}
