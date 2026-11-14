// Sequential colour ramp (low = pale, high = dark red) for belief layers, in RGB.
// The map (rampColor) and the legend (rampGradient) both read these stops, so they cannot drift apart.
export const RAMP: readonly (readonly [number, number, number])[] = [
  [255, 245, 220],
  [253, 204, 138],
  [252, 141, 89],
  [215, 48, 31],
  [127, 0, 0],
];

export function rampColor(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(0.9999, t)) * (RAMP.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = RAMP[i]!;
  const b = RAMP[i + 1]!;
  return [0, 1, 2].map((k) => Math.round(a[k]! + (b[k]! - a[k]!) * f)) as [number, number, number];
}

/** CSS gradient for the legend, evenly spaced like rampColor. */
export function rampGradient(): string {
  const stops = RAMP.map((c, i) => `rgb(${c.join(" ")}) ${Math.round((i / (RAMP.length - 1)) * 100)}%`);
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

/** Lowest opacity per theme: on the dark map the faintest cells need more body to be seen at all. */
export const ALPHA_FLOOR = { light: 40, dark: 90 } as const;

/** Opacity falls as uncertainty grows, so stale or poorly observed cells fade out (never below `floor`). */
export function confidenceAlpha(variance: number, maxVariance: number, floor: number = ALPHA_FLOOR.light): number {
  if (maxVariance <= 0) return 200;
  return Math.max(floor, Math.round(220 - 180 * Math.min(1, variance / maxVariance)));
}

/** Fill strength (0-255) of an area drawn over the 3D city: the colour reads, the buildings still show through. */
export const AREA_ALPHA = 120;

/** Scales an opacity made for a flat map (200 = full) to the see-through strength used over the 3D city. */
export function areaAlpha(alpha: number): number {
  return Math.round((alpha * AREA_ALPHA) / 200);
}
