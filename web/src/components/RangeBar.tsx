import type { Estimate } from "@/api/types";
import { calibrationLabel, formatRange } from "@/lib/format";

/** P5–P95 band with the P50 marker. `max` sets the scale so two bars can be compared. */
export function RangeBar({ e, unit, max, label }: { e: Estimate; unit: string; max: number; label?: string }) {
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  return (
    <div className="space-y-1">
      {label && <div className="label">{label}</div>}
      <div className="relative h-3 rounded bg-stone-100">
        <div className="absolute h-3 rounded bg-roma/30" style={{ left: pct(e.p5), width: `calc(${pct(e.p95)} - ${pct(e.p5)})` }} />
        <div className="absolute h-3 w-0.5 bg-roma" style={{ left: pct(e.p50) }} />
      </div>
      <div className="text-sm font-medium">{formatRange(e, unit)}</div>
      <div className="text-xs text-stone-500">Estimate, not a measurement. {calibrationLabel(e.calibration)}.</div>
    </div>
  );
}
