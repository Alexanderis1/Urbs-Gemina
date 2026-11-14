// Sizes of the 3D markers drawn on the city model (columns rising from the exact spot, with a badge on top).
// Pure numbers only; the drawing itself is in src/map/markers.ts. Reasoning: docs/design-system.md, decision 28.

/** Nominal sizes in screen pixels (at a tilted view). Basis: readable on a phone, never wider than a street at close zoom. */
export const MARKER = {
  /** Height of a place marker (hospital, school, facility). */
  sitePx: 46,
  /** Height of a reading marker: from the lowest to the highest value on screen. */
  valueMinPx: 22,
  valueMaxPx: 76,
  /** Column half-width. */
  radiusPx: 5,
  denseRadiusPx: 3,
  /** Radius of the round badge on top of a column. */
  badgePx: 12,
  /** From this many markers on, columns are slim and only the one under the pointer shows its badge. */
  denseFrom: 400,
  /** Smallest metres per nominal pixel: close up, a column still rises above the buildings around it. */
  minScale: 1.6,
} as const;

/** Latitude of Rome, for the pixel scale. */
const ROME_LAT = 41.9;

/** Ground metres covered by one screen pixel (MapLibre, 512 px tiles). */
export function metersPerPixel(zoom: number, lat: number = ROME_LAT): number {
  return (78271.51696 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
}

/** Metres of column height per nominal pixel at this zoom. */
export function columnScale(zoom: number): number {
  return Math.max(metersPerPixel(zoom), MARKER.minScale);
}

/** Nominal height of a column. `level` is 0..1 for a reading (low to high) and null for a place. */
export function columnPx(level: number | null): number {
  if (level === null) return MARKER.sitePx;
  const t = Math.max(0, Math.min(1, level));
  return MARKER.valueMinPx + (MARKER.valueMaxPx - MARKER.valueMinPx) * t;
}

export function isDense(count: number): boolean {
  return count > MARKER.denseFrom;
}

/** Zoom rounded to a quarter step: marker sizes follow the zoom without redrawing on every frame. */
export function zoomStep(zoom: number): number {
  return Math.round(zoom * 4) / 4;
}
