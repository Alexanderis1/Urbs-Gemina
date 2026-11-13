// Sequential colour ramp (low = pale, high = dark red) for belief layers, in RGB.
const RAMP: [number, number, number][] = [
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

/** Opacity falls as uncertainty grows, so stale or poorly observed cells fade out. */
export function confidenceAlpha(variance: number, maxVariance: number): number {
  if (maxVariance <= 0) return 200;
  return Math.round(220 - 180 * Math.min(1, variance / maxVariance));
}
