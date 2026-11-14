import type { Estimate } from "@/api/types";
import { calibrationLabel, formatRange } from "@/lib/format";
import { texts, tr } from "@/lib/i18n";

const T = texts({
  en: { note: "Estimate, not a measurement.", dashed: (label: string) => `Red dashed line: ${label}.` },
  it: { note: "Stima, non una misura.", dashed: (label: string) => `Linea rossa tratteggiata: ${label}.` },
});

/**
 * P5–P95 band with the P50 marker. `max` sets the scale so two bars can be compared.
 * `tone="whatif"` draws the variant of a what-if; `marker` adds a labelled reference line (e.g. a legal value).
 */
export function RangeBar({
  e,
  unit,
  max,
  label,
  tone = "primary",
  marker,
  note = true,
}: {
  e: Pick<Estimate, "p5" | "p50" | "p95"> & { calibration?: Estimate["calibration"] };
  unit: string;
  max: number;
  label?: string;
  tone?: "primary" | "whatif";
  marker?: { value: number; label: string };
  note?: boolean;
}) {
  const t = tr(T);
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const band = tone === "whatif" ? "bg-whatif/30" : "bg-primary/30";
  const mid = tone === "whatif" ? "bg-whatif" : "bg-link";
  return (
    <div className="space-y-1">
      {label && <div className="label">{label}</div>}
      <div className="relative h-3 rounded-sm bg-sunken ring-1 ring-inset ring-line">
        <div className={`absolute h-3 rounded-sm transition-all duration-500 ease-out ${band}`} style={{ left: pct(e.p5), width: `calc(${pct(e.p95)} - ${pct(e.p5)})` }} />
        <div className={`absolute -top-0.5 h-4 w-0.5 transition-all duration-500 ease-out ${mid}`} style={{ left: pct(e.p50) }} />
        {marker && marker.value <= max && (
          <div className="absolute -top-1.5 h-6 border-l-2 border-dashed border-danger" style={{ left: pct(marker.value) }} title={marker.label} />
        )}
      </div>
      <div className="num text-sm font-medium">{formatRange(e, unit)}</div>
      {note && (
        <div className="hint">
          {t.note}
          {e.calibration ? ` ${calibrationLabel(e.calibration)}.` : ""}
          {marker && marker.value <= max ? ` ${t.dashed(marker.label)}` : ""}
        </div>
      )}
    </div>
  );
}
