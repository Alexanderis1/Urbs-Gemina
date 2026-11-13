import { useMemo, useState } from "react";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { CityMap } from "@/map/CityMap";
import { roman } from "@/lib/area";
import { circlePolygon } from "@/lib/geo";
import { isOk } from "@/api/envelope";
import { KindBadge } from "@/components/Badge";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { buildCitedReport, type Application } from "@/lib/report";
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
  const [site, setSite] = useState<{ lon: number; lat: number; label: string } | null>(null);
  // The application is typed in by the officer (there is no synthetic permit inbox).
  const [app, setApp] = useState<Application>({ operator: "", height_m: "", technology: "", reference: "" });

  async function check(input: { text: string } | { lat: number; lon: number }) {
    setBusy(true);
    setError(null);
    setPlace(null);
    setCtx(null);
    setField(null);
    try {
      let lon: number;
      let lat: number;
      let label: string;
      if ("text" in input) {
        const p = await run<ResolvePlaceResult>("resolve_place", { text: input.text });
        setPlace(p);
        if (!isOk(p)) return;
        ({ lon, lat } = p.result);
        label = p.result.label ?? input.text;
      } else {
        ({ lon, lat } = input);
        label = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
      }
      setSite({ lon, lat, label });
      // radius_m is not sent: context_check takes it from config/thresholds.yaml (antenna_context.radius_m).
      const c = await run<ContextCheckResult>("context_check", { point: [lon, lat] });
      setCtx(c);
      if (!isOk(c)) return;
      // The field estimate covers the same circle, sent as the hub's 64-vertex polygon.
      // The proposed installation is the variant: the estimate covers the field with it added.
      const variant: Record<string, unknown> = { point: [lon, lat] };
      if (app.height_m && Number.isFinite(Number(app.height_m))) variant.height_m = Number(app.height_m);
      if (app.technology) variant.technology = app.technology;
      if (app.operator) variant.operator = app.operator;
      setField(await run<EstimateFieldResult>("estimate_field", { area: circlePolygon(lon, lat, c.result.radius_m), variant }));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const focus = useMemo(() => (site ? { lon: site.lon, lat: site.lat, zoom: 16 } : null), [site]);

  const layers = useMemo(() => {
    if (!site || !ctx || !isOk(ctx)) return [];
    const centre = [site.lon, site.lat] as [number, number];
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
  }, [site, ctx]);

  return (
    <div className="flex h-full">
      <aside className="w-96 shrink-0 space-y-4 overflow-y-auto border-r border-stone-200 bg-white p-4">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void check({ text: query });
          }}
        >
          <div className="label">New application</div>
          <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Site address" />
          <div className="grid grid-cols-2 gap-2">
            <input className="input" placeholder="Operator" value={app.operator} onChange={(e) => setApp({ ...app, operator: e.target.value })} />
            <input className="input" placeholder="Height above ground (m)" inputMode="decimal" value={app.height_m} onChange={(e) => setApp({ ...app, height_m: e.target.value })} />
            <input className="input" placeholder="Technology, e.g. 5G 3.6 GHz" value={app.technology} onChange={(e) => setApp({ ...app, technology: e.target.value })} />
            <input className="input" placeholder="File reference" value={app.reference} onChange={(e) => setApp({ ...app, reference: e.target.value })} />
          </div>
          <button className="btn w-full" disabled={busy}>
            {busy ? "Checking…" : "Check context"}
          </button>
          <p className="text-xs text-stone-500">Or click a point on the map.</p>
        </form>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {(site || place) && (
          <div className="card space-y-1">
            <div className="font-medium">{site?.label ?? "Address not found"}</div>
            {place?.result.municipio != null && (
              <div className="text-xs text-stone-500">
                Municipio {roman(Number(place.result.municipio))}
                {place.result.urban_zone ? ` · zone ${place.result.urban_zone}` : ""}
              </div>
            )}
            {place && <RunMeta env={place} compact />}
          </div>
        )}
        {ctx && !isOk(ctx) && <RunMeta env={ctx} />}
        {ctx && isOk(ctx) && (
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
        {field && !isOk(field) && <RunMeta env={field} />}
        {field && isOk(field) && (
          <div className="card space-y-2">
            <div className="label">Estimated electric field within the circle, with the new antenna</div>
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
        {site && ctx && field && (
          <button
            className="btn-ghost w-full"
            onClick={() => download("permit-context-report.md", buildCitedReport(site.label, place ? [place, ctx, field] : [ctx, field], app))}
          >
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
