import type { Estimate } from "@/api/types";
import { locale, texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    range: (lo: string, hi: string) => `range ${lo} to ${hi}`,
    calibrated: "Calibrated against measurements",
    uncalibrated: "Not calibrated: treat the range as indicative",
  },
  it: {
    range: (lo: string, hi: string) => `intervallo da ${lo} a ${hi}`,
    calibrated: "Calibrato sulle misure",
    uncalibrated: "Non calibrato: l'intervallo è indicativo",
  },
});

// Display rounding: three significant figures below 1, one decimal up to 1,000, whole numbers (grouped) above.
function fmt(n: number): string {
  const a = Math.abs(n);
  if (a > 0 && a < 1) return Number(n.toPrecision(3)).toLocaleString(locale(), { maximumFractionDigits: 20, useGrouping: false });
  if (a >= 1000) return Math.round(n).toLocaleString(locale());
  return (Math.round(n * 10) / 10).toLocaleString(locale(), { maximumFractionDigits: 1, useGrouping: false });
}

/** An estimate is never shown without its range. */
export function formatRange(e: Pick<Estimate, "p5" | "p50" | "p95">, unit: string): string {
  return `${fmt(e.p50)}${unit ? ` ${unit}` : ""} (${tr(T).range(fmt(e.p5), fmt(e.p95))})`;
}

export function calibrationLabel(c: Estimate["calibration"]): string {
  const t = tr(T);
  return c === "calibrated" ? t.calibrated : t.uncalibrated;
}

export function shortId(runId: string): string {
  return runId.slice(0, 10);
}
