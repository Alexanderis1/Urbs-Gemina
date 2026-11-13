import { useState } from "react";
import { AreaPicker } from "@/components/AreaPicker";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { areaToArg, type Area } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import type { Envelope, ScenarioResult } from "@/api/types";

// Scenario kinds from the design (section on the scenario engine). Ids provisional until WS6 publishes them.
const KINDS = [
  { id: "antenna_add", label: "Add an antenna", fields: ["lat", "lon", "height_m"] },
  { id: "antenna_move", label: "Move an antenna", fields: ["site_id", "lat", "lon"] },
  { id: "road_closure", label: "Close a road", fields: ["street"] },
  { id: "population_exposure", label: "Population exposure", fields: [] },
] as const;

export default function ScenarioLab() {
  const { run } = useSession();
  const [kind, setKind] = useState<(typeof KINDS)[number]["id"]>("antenna_add");
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
      setEnv(await run<ScenarioResult>("run_scenario", { kind, area: areaToArg(area), change }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const max = env ? Math.max(env.result.baseline.p95, env.result.variant.p95) * 1.1 : 1;

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
            <h2 className="font-semibold">{env.result.metric}</h2>
            <RangeBar label="Baseline" e={env.result.baseline} unit={env.result.unit} max={max} />
            <RangeBar label="Variant" e={env.result.variant} unit={env.result.unit} max={max} />
            <RunMeta env={env} />
          </>
        )}
      </div>
    </div>
  );
}
