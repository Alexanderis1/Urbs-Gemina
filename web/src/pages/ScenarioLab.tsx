import { useState } from "react";
import { AreaPicker } from "@/components/AreaPicker";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { areaToArg, type Area } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import type { Envelope, ScenarioResult } from "@/api/types";

// Scenario kinds from the design (section on the scenario engine). Ids provisional until WS6 publishes them.
// Kinds the live run_scenario accepts: antenna, population_exposure, road_closure.
const KINDS = [
  { id: "antenna", label: "Add an antenna", fields: ["lat", "lon", "height_m"] },
  { id: "population_exposure", label: "Population exposure", fields: [] },
  { id: "road_closure", label: "Close a road", fields: ["street"] },
] as const;

export default function ScenarioLab() {
  const { run } = useSession();
  const [kind, setKind] = useState<(typeof KINDS)[number]["id"]>("antenna");
  const [area, setArea] = useState<Area>({ type: "municipio", id: "1" });
  const [change, setChange] = useState<Record<string, string>>({ lat: "41.9009", lon: "12.4833", height_m: "30" });
  const [env, setEnv] = useState<Envelope<ScenarioResult> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const spec = KINDS.find((k) => k.id === kind)!;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      // Antenna change in the same shape as estimate_field's variant (add_antennas).
      const c: Record<string, unknown> =
        kind === "antenna"
          ? {
              add_antennas: [
                {
                  lon: Number(change.lon),
                  lat: Number(change.lat),
                  ...(change.height_m ? { height_m: Number(change.height_m) } : {}),
                },
              ],
            }
          : change;
      setEnv(await run<ScenarioResult>("run_scenario", { kind, area: areaToArg(area), change: c }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const b = env?.result.baseline;
  const v = env?.result.variant;
  const max = b && v ? Math.max(b.p95, v.p95) * 1.1 : 1;
  const extra = env ? Object.entries(env.result).filter(([k]) => !["baseline", "variant", "kind", "metric", "unit"].includes(k)) : [];

  return (
    <div className="mx-auto grid max-w-5xl gap-4 p-4 md:grid-cols-[18rem_1fr]">
      <div className="card space-y-4">
        <div className="space-y-1">
          <div className="label">Scenario</div>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            {KINDS.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
        <AreaPicker area={area} onChange={setArea} />
        {area.type === "city" && (
          <p className="text-xs text-amber-700">
            Heavy simulations run on a district. The tool will refuse areas above the configured size; pick a municipio or zone.
          </p>
        )}
        {spec.fields.length > 0 && (
          <div className="space-y-1">
            <div className="label">Change</div>
            {spec.fields.map((f) => (
              <input key={f} className="input" placeholder={f} value={change[f] ?? ""} onChange={(e) => setChange({ ...change, [f]: e.target.value })} />
            ))}
          </div>
        )}
        <button className="btn w-full" onClick={() => void go()} disabled={busy}>
          {busy ? "Running…" : "Compare baseline and variant"}
        </button>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
      <div className="card space-y-4">
        {!env && <p className="text-sm text-stone-500">Pick a scenario and an area, then run it.</p>}
        {env && (
          <>
            {env.result.metric && <h2 className="font-semibold">{env.result.metric}</h2>}
            {b && <RangeBar label="Baseline" e={b} unit={env.result.unit ?? ""} max={max} />}
            {v && <RangeBar label="Variant" e={v} unit={env.result.unit ?? ""} max={max} />}
            {extra.length > 0 && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-xs">
                {extra.map(([k, val]) => (
                  <div key={k} className="contents">
                    <dt className="font-medium">{k.replace(/_/g, " ")}</dt>
                    <dd className="break-all text-stone-600">{typeof val === "object" ? JSON.stringify(val) : String(val)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <RunMeta env={env} />
          </>
        )}
      </div>
    </div>
  );
}
