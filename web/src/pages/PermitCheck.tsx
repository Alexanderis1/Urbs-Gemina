import { useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { CityMap } from "@/map/CityMap";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { Callout, EmptyState, Field, MapFloat, Panel, Section, Skeleton, Spinner, Stat, Workspace } from "@/components/ui";
import { Download, MapPin, RadioTower } from "lucide-react";
import { useTheme } from "@/lib/useTheme";
import { buildCitedReport, type Application } from "@/lib/report";
import { contextRows, contextSummary } from "@/lib/context";
import { useSession } from "@/lib/runlog";
import { isOk } from "@/api/envelope";
import { isSampleMode, proxyFetch } from "@/api/client";
import type { ContextCheckResult, Envelope, EstimateFieldResult, ResolvePlaceResult } from "@/api/types";
import { errorText } from "@/lib/errors";

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
  const { palette } = useTheme();
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
      setError(errorText(e));
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
    const [r, g, b] = palette.accent;
    return [
      new ScatterplotLayer({
        id: "radius",
        data: [centre],
        getPosition: (d: [number, number]) => d,
        getRadius: ctx.result.radius_m,
        radiusUnits: "meters",
        filled: true,
        stroked: true,
        getFillColor: [r, g, b, 30],
        getLineColor: [r, g, b, 255],
        lineWidthMinPixels: 2,
        updateTriggers: { getFillColor: [r, g, b], getLineColor: [r, g, b] },
      }),
      new ScatterplotLayer({
        id: "site",
        data: [centre],
        getPosition: (d: [number, number]) => d,
        getFillColor: [r, g, b],
        radiusMinPixels: 7,
        updateTriggers: { getFillColor: [r, g, b] },
      }),
    ];
  }, [site, ctx, palette]);

  const thresholds = field && isOk(field) ? Object.entries(field.result.exceedance ?? {}) : [];
  const firstLimit = thresholds.find(([, t]) => t.threshold_v_per_m != null);
  const markerValue = firstLimit?.[1].threshold_v_per_m ?? null;
  const ready = !busy && !!site && !!ctx && !!field;
  const fieldEmpty = !busy && !place;

  return (
    <Workspace
      panel={
        <Panel
          title="Permit check"
          icon={RadioTower}
          subtitle="Context for a new antenna application"
          width="w-[26rem]"
          footer={
            <button type="button" className="btn-ghost w-full" disabled={!ready} onClick={() => void downloadReport()}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Download cited report
            </button>
          }
        >
          <Section title="Application">
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void check({ text: query });
              }}
            >
              <Field label="Site address">
                <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Operator">
                  <input className="input" value={app.operator} onChange={(e) => setApp({ ...app, operator: e.target.value })} />
                </Field>
                <Field label="Height above ground (m)">
                  <input className="input" inputMode="decimal" value={app.height_m} onChange={(e) => setApp({ ...app, height_m: e.target.value })} />
                </Field>
                <Field label="Band">
                  <select
                    className="input"
                    value={band}
                    onChange={(e) => {
                      setBand(e.target.value);
                      setApp({ ...app, technology: e.target.value ? `${e.target.value} MHz` : "" });
                    }}
                  >
                    <option value="">Not specified</option>
                    {BANDS.map((b) => (
                      <option key={b} value={b}>
                        {b} MHz
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="File reference">
                  <input className="input" value={app.reference} onChange={(e) => setApp({ ...app, reference: e.target.value })} />
                </Field>
              </div>
              <button type="submit" className="btn w-full" disabled={busy}>
                {busy && <Spinner />}
                {busy ? "Checking…" : "Check context"}
              </button>
              <p className="hint">Or click a point on the map.</p>
            </form>
          </Section>

          {error && <Callout tone="error">{error}</Callout>}

          {busy && (
            <div className="space-y-3" aria-busy="true">
              <div className="card space-y-2">
                <Skeleton lines={2} />
              </div>
              <div className="card space-y-2">
                <Skeleton lines={4} />
              </div>
              <div className="card space-y-2">
                <Skeleton lines={3} />
              </div>
            </div>
          )}

          {fieldEmpty && !error && (
            <EmptyState icon={MapPin} title="No site checked yet">
              Enter an address or click the map to see the sensitive sites within the legal radius and an estimate of the electric field.
            </EmptyState>
          )}

          {!busy && place && (
            <div className="card animate-rise-in space-y-2">
              <h2 className="label">Site</h2>
              {place.result.found ? (
                <>
                  <div className="text-sm font-semibold">{site?.label ?? place.result.label}</div>
                  {place.result.municipio?.name && (
                    <div className="hint">
                      {/^municipio/i.test(place.result.municipio.name) ? place.result.municipio.name : `Municipio ${place.result.municipio.name}`}
                      {place.result.urban_zone?.name ? ` · ${place.result.urban_zone.name} (${place.result.urban_zone.id})` : ""}
                    </div>
                  )}
                </>
              ) : (
                <Callout tone="warn" title="Address not found">
                  Check the spelling or click the point on the map.
                </Callout>
              )}
              <RunMeta env={place} compact />
            </div>
          )}

          {!busy && ctx && !isOk(ctx) && (
            <div className="card animate-rise-in">
              <RunMeta env={ctx} />
            </div>
          )}
          {!busy && ctx && isOk(ctx) && summary && (
            <div className="card animate-rise-in space-y-3">
              <h2 className="label">Within {ctx.result.radius_m} m</h2>
              <Callout tone="info">{ctx.result.meaning}</Callout>
              <Stat label="Sensitive sites" value={summary.sensitiveHits} />
              {rows.length === 0 ? (
                <p className="text-sm text-muted">Nothing found within the radius.</p>
              ) : (
                <ul className="divide-y divide-line text-sm">
                  {rows.map((r, i) => (
                    <li key={`${r.layer}-${i}`} className="flex items-baseline justify-between gap-3 py-1.5">
                      <span className="min-w-0 break-words">
                        <span className="font-semibold">{r.layerLabel}</span> · {r.name}
                      </span>
                      <span className="num whitespace-nowrap">{Math.round(r.distance_m)} m</span>
                    </li>
                  ))}
                </ul>
              )}
              {summary.unavailable.length > 0 && <Callout tone="warn">Not checked: {summary.unavailable.join(", ")}</Callout>}
              <RunMeta env={ctx} />
            </div>
          )}

          {!busy && field && !isOk(field) && (
            <div className="card animate-rise-in">
              <RunMeta env={field} />
            </div>
          )}
          {!busy && field && isOk(field) && (
            <div className="card animate-rise-in space-y-3">
              <h2 className="label">Electric field at the site</h2>
              <p className="text-sm font-semibold">{band ? "With the new antenna" : "Today (choose a band to add the new antenna)"}</p>
              <RangeBar
                e={field.result}
                unit={field.result.unit}
                max={Math.max(field.result.p95 * 1.2, markerValue != null ? markerValue * 1.15 : 0, 1)}
                marker={markerValue != null && firstLimit ? { value: markerValue, label: `${firstLimit[0].replace(/_/g, " ")} (${markerValue} V/m)` } : undefined}
              />
              {thresholds.length > 0 && (
                <ul className="divide-y divide-line text-sm">
                  {thresholds.map(([k, t]) => (
                    <li key={k} className="py-1.5">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="min-w-0 break-words">
                          <span className="font-semibold">{k.replace(/_/g, " ")}</span>
                          {t.threshold_v_per_m != null && <span className="num"> · {t.threshold_v_per_m} V/m</span>}
                        </span>
                        <span className="num whitespace-nowrap" title="Probability of exceeding">
                          {Math.round((t.probability ?? 0) * 100)}%
                        </span>
                      </div>
                      <div className="hint">Probability of exceeding{t.source ? ` · ${t.source}` : ""}</div>
                    </li>
                  ))}
                </ul>
              )}
              {field.result.model && <p className="hint">Model: {field.result.model}</p>}
              {field.result.averaging_note && <p className="hint">{field.result.averaging_note}</p>}
              {field.result.baseline?.credit && <p className="hint">{field.result.baseline.credit}</p>}
              <RunMeta env={field} />
            </div>
          )}
        </Panel>
      }
    >
      <CityMap layers={layers} initialZoom={14} pitch={45} focus={focus} onClick={(p) => void check(p)} />
      {site && (
        <MapFloat position="top-left" className="max-w-sm">
          <div className="text-sm font-semibold">{site.label}</div>
          {ctx && isOk(ctx) && <div className="hint">Context radius {ctx.result.radius_m} m</div>}
        </MapFloat>
      )}
    </Workspace>
  );
}
