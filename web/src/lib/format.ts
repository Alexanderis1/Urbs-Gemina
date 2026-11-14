import type { Estimate } from "@/api/types";

// Display rounding: three significant figures below 1, one decimal up to 1,000, whole numbers (grouped) above.
function fmt(n: number): string {
  const a = Math.abs(n);
  if (a > 0 && a < 1) return String(Number(n.toPrecision(3)));
  if (a >= 1000) return Math.round(n).toLocaleString("en-GB");
  return (Math.round(n * 10) / 10).toString();
}

/** An estimate is never shown without its range. */
export function formatRange(e: Pick<Estimate, "p5" | "p50" | "p95">, unit: string): string {
  return `${fmt(e.p50)}${unit ? ` ${unit}` : ""} (range ${fmt(e.p5)} to ${fmt(e.p95)})`;
}

export function calibrationLabel(c: Estimate["calibration"]): string {
  return c === "calibrated" ? "Calibrated against measurements" : "Not calibrated: treat the range as indicative";
}

export function shortId(runId: string): string {
  return runId.slice(0, 10);
}
