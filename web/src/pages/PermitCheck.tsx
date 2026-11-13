import { useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { CityMap } from "@/map/CityMap";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { buildCitedReport, type Application } from "@/lib/report";
import { contextRows, contextSummary } from "@/lib/context";
import { useSession } from "@/lib/runlog";
import { isOk } from "@/api/envelope";
import { isSampleMode, proxyFetch } from "@/api/client";
import type { ContextCheckResult, Envelope, EstimateFieldResult, ResolvePlaceResult } from "@/api/types";

const BANDS = [800, 900, 1800, 2100, 3500] as const;

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
  const [band, setBand] = useState<string>("");

  const antenna = (lon: number, lat: number) => {
    const a: Record<string, unknown> = { lon, lat };
    if (app.height_m && Number.isFinite(Number(app.height_m))) a.height_m = Number(app.height_m);
    if (band) a.band_mhz = Number(band);
    return a;
  };

  async function check(input: { text: string } | { lat: number; lon: number }) {
    setBusy(true);
    setError(null);
    setPlace(null);
    setCtx(null);
    setField(null);
    try {
      const text = "text" in input ? input.text : `${input.lat.toFixed(6)}, ${input.lon.toFixed(6)}`;
      const p = await run<ResolvePlaceResult>("resolve_place", { text });
      setPlace(p);
      if (!isOk(p) || !p.result.found) return;
      const { lon, lat } = p.result;
      setSite({ lon, lat, label: p.result.label ?? text });
      // radius_m is not sent: context_check takes it from config/thresholds.yaml (antenna_context.radius_m).
      // The proposed antenna is the variant: the estimate is the field at the site with it added.
      // The tool needs a band (or EIRP) for the antenna; without one, only today's field is estimated.
      const fieldInputs: Record<string, unknown> = band
        ? { point: [lon, lat], variant: { add_antennas: [antenna(lon, lat)] } }
        : { point: [lon, lat] };
      const [c, f] = await Promise.all([
        run<ContextCheckResult>("context_check", { point: [lon, lat] }),
        run<EstimateFieldResult>("estimate_field", fieldInputs),
      ]);
      setCtx(c);
      setField(f);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function downloadReport() {
    if (!site || !ctx || !field) return;
    if (!isSampleMode) {
      // Official cited report from the tool API (WS4), office tier through the edge function.
      const res = await proxyFetch("/reports/permit.md", {
        place: query,
        point: [site.lon, site.lat],
        ...(band ? { proposed_antennas: [antenna(site.lon, site.lat)] } : {}),
      });
      if (res.ok) {
        const header = [
          "<!-- Application details entered by the officer -->",
          `Operator: ${app.operator || "not given"} · Technology: ${app.technology || "not given"} · File: ${app.reference || "not given"}`,
          "",
        ].join("\n");
        return download("permit-context-report.md", header + (await res.text()));
      }
      setError(`Report not available (HTTP ${res.status}); downloaded the local summary instead.`);
    }
    download("permit-context-report.md", buildCitedReport(site.label, place ? [place, ctx, field] : [ctx, field], app));
  }

  const focus = useMemo(() => (site ? { lon: site.lon, lat: site.lat, zoom: 16 } : null), [site]);
  const rows = ctx && isOk(ctx) ? contextRows(ctx.result) : [];
  const summary = ctx && isOk(ctx) ? contextSummary(ctx.result) : null;

  const layers = useMemo(() => {
    if (!site || !ctx || !isOk(ctx)) return [];
    const centre = [site.lon, site.lat] as [number, number];
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
    ];
  }, [site, ctx]);

  const thresholds = field && isOk(field) ? Object.entries(field.result.exceedance ?? {}) : [];

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
            <select
              className="input"
              value={band}
              onChange={(e) => {
                setBand(e.target.value);
                setApp({ ...app, technology: e.target.value ? `${e.target.value} MHz` : "" });
              }}
            >
              <option value="">Band (MHz)</option>
              {BANDS.map((b) => (
                <option key={b} value={b}>
                  {b} MHz
                </option>
              ))}
            </select>
            <input className="input" placeholder="File reference" value={app.reference} onChange={(e) => setApp({ ...app, reference: e.target.value })} />
          </div>
          <button className="btn w-full" disabled={busy}>
            {busy ? "Checking…" : "Check context"}
          </button>
          <p className="text-xs text-stone-500">Or click a point on the map.</p>
        </form>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {place && (
          <div className="card space-y-1">
            <div className="font-medium">{place.result.found ? (site?.label ?? place.result.label) : "Address not found"}</div>
            {place.result.municipio?.name && (
              <div className="text-xs text-stone-500">
                {/^municipio/i.test(place.result.municipio.name) ? place.result.municipio.name : `Municipio ${place.result.municipio.name}`}
                {place.result.urban_zone?.name ? ` · ${place.result.urban_zone.name} (${place.result.urban_zone.id})` : ""}
              </div>
            )}
            <RunMeta env={place} compact />
          </div>
        )}
        {ctx && !isOk(ctx) && <RunMeta env={ctx} />}
        {ctx && isOk(ctx) && summary && (
          <div className="card space-y-2">
            <div className="label">Within {ctx.result.radius_m} m</div>
            <p className="text-xs italic text-stone-600">{ctx.result.meaning}</p>
            <p className="text-sm">
              Sensitive sites: <b>{summary.sensitiveHits}</b>
            </p>
            {rows.length === 0 && <p className="text-sm text-stone-500">Nothing found within the radius.</p>}
            <ul className="divide-y divide-stone-100 text-sm">
              {rows.map((r, i) => (
                <li key={`${r.layer}-${i}`} className="flex items-center justify-between gap-2 py-1">
                  <span>
                    <span className="font-medium">{r.layerLabel}</span> · {r.name}
                  </span>
                  <span className="whitespace-nowrap">{Math.round(r.distance_m)} m</span>
                </li>
              ))}
            </ul>
            {summary.unavailable.length > 0 && (
              <p className="text-xs text-amber-700">Not checked (layer not available): {summary.unavailable.join(", ")}</p>
            )}
            <RunMeta env={ctx} />
          </div>
        )}
        {field && !isOk(field) && <RunMeta env={field} />}
        {field && isOk(field) && (
          <div className="card space-y-2">
            <div className="label">
              {band ? "Estimated electric field at the site, with the new antenna" : "Estimated electric field at the site today (pick a band to add the new antenna)"}
            </div>
            <RangeBar e={field.result} unit={field.result.unit} max={Math.max(field.result.p95 * 1.2, 1)} />
            {field.result.model && <p className="text-xs text-stone-500">Model: {field.result.model}</p>}
            {field.result.averaging_note && <p className="text-xs text-stone-500">{field.result.averaging_note}</p>}
            {thresholds.map(([k, t]) => (
              <p key={k} className="text-sm">
                Probability of exceeding the {k.replace(/_/g, " ")}
                {t.threshold_v_per_m != null ? ` (${t.threshold_v_per_m} V/m)` : ""}: <b>{Math.round((t.probability ?? 0) * 100)}%</b>
                {t.source && <span className="block text-xs text-stone-500">{t.source}</span>}
              </p>
            ))}
            {field.result.baseline?.credit && <p className="text-xs text-stone-500">{field.result.baseline.credit}</p>}
            <RunMeta env={field} />
          </div>
        )}
        {site && ctx && field && (
          <button className="btn-ghost w-full" onClick={() => void downloadReport()}>
            Download cited report
          </button>
        )}
      </aside>
      <div className="flex-1">
        <CityMap layers={layers} initialZoom={14} pitch={45} focus={focus} onClick={(p) => void check(p)} />
      </div>
    </div>
  );
}
