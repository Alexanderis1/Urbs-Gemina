import type { Estimate } from "@/api/types";

const fmt = (n: number) => (Math.round(n * 10) / 10).toString();

/** An estimate is never shown without its range. */
export function formatRange(e: Pick<Estimate, "p5" | "p50" | "p95">, unit: string): string {
  return `${fmt(e.p50)} ${unit} (range ${fmt(e.p5)} to ${fmt(e.p95)})`;
}

export function calibrationLabel(c: Estimate["calibration"]): string {
  return c === "calibrated" ? "Calibrated against measurements" : "Not calibrated: treat the range as indicative";
}

export function shortId(runId: string): string {
  return runId.slice(0, 10);
}
