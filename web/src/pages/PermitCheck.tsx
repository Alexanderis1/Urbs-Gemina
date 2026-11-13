import { useMemo, useState } from "react";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { CityMap } from "@/map/CityMap";
import { KindBadge } from "@/components/Badge";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { buildCitedReport } from "@/lib/report";
import { useSession } from "@/lib/runlog";
import type { ContextCheckResult, ContextItem, Envelope, EstimateFieldResult, ResolvePlaceResult } from "@/api/types";

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function PermitCheck() {
  const { run } = useSession();
  const [query, setQuery] = useState("Via Nazionale 194, Roma");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [place, setPlace] = useState<Envelope<ResolvePlaceResult> | null>(null);
  const [ctx, setCtx] = useState<Envelope<ContextCheckResult> | null>(null);
  const [field, setField] = useState<Envelope<EstimateFieldResult> | null>(null);

  async function check(input: { query: string } | { lat: number; lon: number }) {
    setBusy(true);
    setError(null);
    try {
      const p = await run<ResolvePlaceResult>("resolve_place", input);
      const { lat, lon } = p.result;
      setPlace(p);
      // radius_m is not sent: context_check takes it from config/thresholds.yaml (antenna_context.radius_m).
      const [c, f] = await Promise.all([
        run<ContextCheckResult>("context_check", { lat, lon }),
        run<EstimateFieldResult>("estimate_field", { lat, lon }),
      ]);
      setCtx(c);
      setField(f);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const focus = useMemo(() => (place ? { lon: place.result.lon, lat: place.result.lat, zoom: 16 } : null), [place]);

  const layers = useMemo(() => {
    if (!place || !ctx) return [];
    const centre = [place.result.lon, place.result.lat] as [number, number];
    const items = ctx.result.items.filter((i): i is ContextItem & { lat: number; lon: number } => i.lat != null && i.lon != null);
    return [
      new ScatterplotLayer({
        id: "radius",
        data: [centre],
        getPosition: (d: [number, number]) => d,
        getRadius: ctx.result.radius_m,
        radiusUnits: "meters",
        filled: true,
        stroked: true,
        getFillColor: [139, 30, 45, 30],
        getLineColor: [139, 30, 45, 255],
        lineWidthMinPixels: 2,
      }),
      new ScatterplotLayer({
        id: "site",
        data: [centre],
        getPosition: (d: [number, number]) => d,
        getFillColor: [139, 30, 45],
        radiusMinPixels: 7,
      }),
      new ScatterplotLayer({
        id: "context",
        data: items,
        getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
        getFillColor: [37, 99, 235],
        radiusMinPixels: 5,
      }),
      new TextLayer({
        id: "context-labels",
        data: items,
        getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
        getText: (d: ContextItem) => d.category,
        getSize: 12,
        getPixelOffset: [0, -14],
        getColor: [30, 30, 30],
      }),
    ];
  }, [place, ctx]);

  return (
    <div className="flex h-full">
      <aside className="w-96 shrink-0 space-y-4 overflow-y-auto border-r border-stone-200 bg-white p-4">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void check({ query });
          }}
        >
          <div className="label">Proposed antenna site</div>
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Address or lat, lon" />
          <button className="btn w-full" disabled={busy}>
            {busy ? "Checking…" : "Check context"}
          </button>
          <p className="text-xs text-stone-500">Or click a point on the map.</p>
        </form>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {place && (
          <div className="card space-y-1">
            <div className="font-medium">{place.result.label}</div>
            {place.result.municipio && <div className="text-xs text-stone-500">Municipio {place.result.municipio}</div>}
            <RunMeta env={place} compact />
          </div>
        )}
        {ctx && (
          <div className="card space-y-2">
            <div className="label">Within {ctx.result.radius_m} m</div>
            <p className="text-xs italic text-stone-600">{ctx.result.note}</p>
            <ul className="divide-y divide-stone-100 text-sm">
              {ctx.result.items.map((i) => (
                <li key={`${i.category}-${i.name}`} className="flex items-center justify-between gap-2 py-1">
                  <span>
                    <span className="font-medium">{i.category}</span> · {i.name}
                  </span>
                  <span className="flex items-center gap-1 whitespace-nowrap">
                    {i.distance_m} m <KindBadge kind={i.data_kind} />
                  </span>
                </li>
              ))}
            </ul>
            <RunMeta env={ctx} />
          </div>
        )}
        {field && (
          <div className="card space-y-2">
            <div className="label">Estimated electric field at the site</div>
            <RangeBar e={field.result.estimate} unit={field.result.unit} max={Math.max(field.result.estimate.p95 * 1.2, 1)} />
            {field.result.exceedance_probability != null && (
              <p className="text-sm">
                Probability of exceeding the {field.result.threshold_ref ?? "attention value"}:{" "}
                <b>{Math.round(field.result.exceedance_probability * 100)}%</b>
              </p>
            )}
            <RunMeta env={field} />
          </div>
        )}
        {place && ctx && field && (
          <button className="btn-ghost w-full" onClick={() => download("permit-context-report.md", buildCitedReport(place.result.label, [place, ctx, field]))}>
            Download cited report
          </button>
        )}
      </aside>
      <div className="flex-1">
        <CityMap
          layers={layers}
          initialZoom={14}
          pitch={45}
          focus={focus}
          onClick={(p) => void check(p)}
        />
      </div>
    </div>
  );
}
