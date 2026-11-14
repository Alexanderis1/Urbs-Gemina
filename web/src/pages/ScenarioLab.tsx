import { Fragment, useMemo, useState, type ReactNode } from "react";
import { GeoJsonLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import {
  Biohazard,
  CloudRain,
  Crosshair,
  FlaskConical,
  MapPin,
  Play,
  RadioTower,
  Siren,
  ThermometerSun,
  TrafficCone,
  Users,
  Waves,
  X,
  type LucideIcon,
} from "lucide-react";
import { CityMap, type MapFocus } from "@/map/CityMap";
import { boundsOf } from "@/lib/geo";
import { AreaPicker } from "@/components/AreaPicker";
import { KindBadge } from "@/components/Badge";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { Callout, Field, MapFloat, Panel, Section, Segmented, Skeleton, Spinner, Stat, Workspace } from "@/components/ui";
import { areaLabel, areaToArg, type Area } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import { useTheme } from "@/lib/useTheme";
import type { Envelope, ScenarioResult } from "@/api/types";
import {
  buildScenarioChange,
  changeProblem,
  isHeavy,
  isUnknownKindError,
  resolveKind,
  scenarioSpec,
  SCENARIO_BANDS,
  SCENARIO_GAUGES,
  SCENARIO_GROUPS,
  SCENARIO_SERVICES,
  SCENARIO_SUBSTANCES,
  SCENARIOS,
  type ScenarioTile,
} from "@/lib/scenario";
import { fmtNumber, keyFigures, MAX_ROWS, rangeText, summariseScenario, unitFor, type Quantile } from "@/lib/scenarioResult";

const ICONS: Record<ScenarioTile, LucideIcon> = {
  river_flood: Waves,
  rain_flood: CloudRain,
  heatwave: ThermometerSun,
  chemical_plume: Biohazard,
  road_closure: TrafficCone,
  emergency_access: Siren,
  antenna: RadioTower,
  population_exposure: Users,
};

type Form = Record<string, string>;
type Rgb = [number, number, number];
/** Theme surface colour (hex in the palette) as RGB, to outline dots so they read on top of footprints. */
const hexRgb = (hex: string): Rgb => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Rgb;
const rgb = (c: Rgb, a = 1) => `rgb(${c.join(" ")} / ${a})`;

const initialForms = () => Object.fromEntries(SCENARIOS.map((s) => [s.id, { ...s.defaults }])) as Record<ScenarioTile, Form>;

/** Point placed by the officer, when the kind needs one and the form holds valid coordinates. */
function placedPoint(tile: ScenarioTile, f: Form): [number, number] | null {
  if (!scenarioSpec(tile).usesPoint || (tile === "chemical_plume" && f.place === "site")) return null;
  const lon = Number(f.lon);
  const lat = Number(f.lat);
  return f.lon?.trim() && f.lat?.trim() && Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null;
}

// --- Small form pieces ------------------------------------------------------------------------------------

function NumField({ label, unit, value, onChange, hint, placeholder }: { label: string; unit?: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string }) {
  return (
    <Field label={unit ? `${label} (${unit})` : label} hint={hint}>
      <input className="input num" inputMode="decimal" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function TextField({ label, value, onChange, hint, placeholder, list }: { label: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string; list?: string }) {
  return (
    <Field label={label} hint={hint}>
      <input className="input" value={value} placeholder={placeholder} list={list} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function PointFields({ f, set, what }: { f: Form; set: (k: string, v: string) => void; what: string }) {
  const placed = f.lon?.trim() && f.lat?.trim();
  return (
    <div className="space-y-2 rounded border border-dashed border-whatif/60 bg-whatif/5 p-2.5">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-whatif">
        <Crosshair className="h-3.5 w-3.5" aria-hidden="true" />
        {placed ? `Click the map to move the ${what}` : `Click the map to place the ${what}`}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <NumField label="Longitude" value={f.lon ?? ""} onChange={(v) => set("lon", v)} placeholder="12.4833" />
        <NumField label="Latitude" value={f.lat ?? ""} onChange={(v) => set("lat", v)} placeholder="41.9009" />
      </div>
    </div>
  );
}

function ChangeForm({ tile, f, set }: { tile: ScenarioTile; f: Form; set: (k: string, v: string) => void }) {
  const two = "grid grid-cols-2 gap-2";
  switch (tile) {
    case "river_flood":
      return (
        <>
          <Segmented
            label="How to set the river"
            value={(f.mode ?? "rise") as "rise" | "level" | "forecast"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "rise", label: "Rise" },
              { id: "level", label: "Gauge level" },
              { id: "forecast", label: "Forecast" },
            ]}
          />
          {f.mode === "level" || f.mode === "forecast" ? (
            <Field label="River gauge">
              <select className="input" value={f.gauge} onChange={(e) => set("gauge", e.target.value)}>
                {SCENARIO_GAUGES.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.label}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          {f.mode === "level" && <NumField label="Water level at the gauge" unit="m" value={f.level_m ?? ""} onChange={(v) => set("level_m", v)} />}
          {f.mode === "forecast" && <p className="hint">Uses the highest level in the river forecast for the coming days.</p>}
          {(f.mode ?? "rise") === "rise" && (
            <NumField label="River rise above normal" unit="m" value={f.rise_m ?? ""} onChange={(v) => set("rise_m", v)} />
          )}
        </>
      );
    case "rain_flood":
      return (
        <>
          <Segmented
            label="Where the rain comes from"
            value={(f.mode ?? "rain") as "rain" | "radar" | "forecast"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "rain", label: "Amount" },
              { id: "radar", label: "Radar now" },
              { id: "forecast", label: "Forecast" },
            ]}
          />
          {(f.mode ?? "rain") === "rain" ? (
            <div className={two}>
              <NumField label="Rain" unit="mm" value={f.rain_mm ?? ""} onChange={(v) => set("rain_mm", v)} />
              <NumField label="Over" unit="hours" value={f.duration_h ?? ""} onChange={(v) => set("duration_h", v)} />
            </div>
          ) : (
            <p className="hint">{f.mode === "radar" ? "Uses the rain the radar sees now." : "Uses the rain forecast."}</p>
          )}
          <NumField
            label="High river, optional"
            unit="m"
            value={f.river_rise_m ?? ""}
            onChange={(v) => set("river_rise_m", v)}
            placeholder="e.g. 3"
            hint="A high Tiber blocks sewer outfalls. Leave empty to ignore."
          />
        </>
      );
    case "heatwave":
      return (
        <>
          <Segmented
            label="Temperatures"
            value={(f.temperature ?? "forecast") as "forecast" | "manual"}
            onChange={(v) => set("temperature", v)}
            options={[
              { id: "forecast", label: "Forecast" },
              { id: "manual", label: "Enter values" },
            ]}
          />
          {f.temperature === "manual" ? (
            <div className={two}>
              <NumField label="Day maximum" unit="°C" value={f.tmax_c ?? ""} onChange={(v) => set("tmax_c", v)} />
              <NumField label="Night minimum" unit="°C" value={f.tmin_c ?? ""} onChange={(v) => set("tmin_c", v)} />
            </div>
          ) : (
            <p className="hint">Uses the temperature forecast for the area.</p>
          )}
          <div className="label pt-1">Changes to test, optional</div>
          <div className={two}>
            <NumField label="Tree cover added" unit="%" value={f.trees_pct ?? ""} onChange={(v) => set("trees_pct", v)} placeholder="e.g. 10" />
            <NumField label="Sealed ground removed" unit="%" value={f.depave_pct ?? ""} onChange={(v) => set("depave_pct", v)} placeholder="e.g. 10" />
          </div>
        </>
      );
    case "chemical_plume":
      return (
        <>
          <Segmented
            label="Where the release happens"
            value={(f.place ?? "point") as "point" | "site"}
            onChange={(v) => set("place", v)}
            options={[
              { id: "point", label: "Point on map" },
              { id: "site", label: "Named site" },
            ]}
          />
          {f.place === "site" ? (
            <TextField label="Hazardous site" value={f.site ?? ""} onChange={(v) => set("site", v)} hint="Name of a listed hazardous (Seveso) site." />
          ) : (
            <PointFields f={f} set={set} what="release point" />
          )}
          <div className={two}>
            <TextField label="Substance" value={f.substance ?? ""} onChange={(v) => set("substance", v)} list="scenario-substances" />
            <NumField label="Release rate" unit="kg/s" value={f.release_kg_s ?? ""} onChange={(v) => set("release_kg_s", v)} />
          </div>
          <datalist id="scenario-substances">
            {SCENARIO_SUBSTANCES.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <Segmented
            label="Wind"
            value={(f.wind ?? "forecast") as "forecast" | "manual"}
            onChange={(v) => set("wind", v)}
            options={[
              { id: "forecast", label: "Wind forecast" },
              { id: "manual", label: "Enter wind" },
            ]}
          />
          {f.wind === "manual" && (
            <div className={two}>
              <NumField label="Wind speed" unit="m/s" value={f.wind_speed_ms ?? ""} onChange={(v) => set("wind_speed_ms", v)} />
              <NumField label="Blowing from" unit="degrees" value={f.wind_from_deg ?? ""} onChange={(v) => set("wind_from_deg", v)} hint="270 = from the west" />
            </div>
          )}
        </>
      );
    case "road_closure":
      return (
        <>
          <Segmented
            label="Kind of change"
            value={(f.mode ?? "close") as "close" | "event" | "roadworks"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "close", label: "Close a road" },
              { id: "event", label: "Public event" },
              { id: "roadworks", label: "Roadworks" },
            ]}
          />
          <TextField label="Street" value={f.street ?? ""} onChange={(v) => set("street", v)} placeholder="e.g. Via del Corso" />
          {f.mode === "event" && <NumField label="People attending" value={f.attendees ?? ""} onChange={(v) => set("attendees", v)} />}
          {f.mode === "roadworks" && <NumField label="Lanes closed" value={f.lanes_closed ?? ""} onChange={(v) => set("lanes_closed", v)} />}
        </>
      );
    case "emergency_access":
      return (
        <>
          <Segmented
            label="Emergency service"
            value={(f.service ?? "fire") as "fire" | "ambulance" | "police"}
            onChange={(v) => set("service", v)}
            options={SCENARIO_SERVICES.map((s) => ({ id: s.id, label: s.label }))}
          />
          <TextField label="Street to close" value={f.street ?? ""} onChange={(v) => set("street", v)} placeholder="e.g. Via Ostiense" />
          <NumField
            label="River flood at the same time, optional"
            unit="m rise"
            value={f.flood_rise_m ?? ""}
            onChange={(v) => set("flood_rise_m", v)}
            placeholder="e.g. 3"
            hint="Flooded streets are closed too. Leave empty to ignore."
          />
        </>
      );
    case "antenna":
    case "population_exposure":
      return (
        <>
          <PointFields f={f} set={set} what="antenna" />
          <div className={two}>
            <NumField label="Height above ground" unit="m" value={f.height_m ?? ""} onChange={(v) => set("height_m", v)} />
            <Field label="Frequency band">
              <select className="input" value={f.band ?? "3500"} onChange={(e) => set("band", e.target.value)}>
                {SCENARIO_BANDS.map((b) => (
                  <option key={b} value={b}>
                    {b} MHz
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </>
      );
  }
}

// --- Result pieces ----------------------------------------------------------------------------------------

const rangeNote = (q: Quantile) => rangeText(q);

function ResultView({ env, title }: { env: Envelope<ScenarioResult>; title: string }) {
  const s = useMemo(() => summariseScenario(env.result), [env]);
  // A nested pair (e.g. residents beyond the target time) carries its own meaning; the top-level one uses `unit`.
  const unit = s.compare?.path ? unitFor(s.compare.path) : (env.result.unit ?? "");
  // People and extent first; what is shown as a key figure is not repeated further down.
  const headline = useMemo(() => keyFigures(s), [s]);
  const shown = new Set(headline.map((f) => f.path));
  const rest = s.quantiles.filter((q) => !shown.has(q.path));
  const facts = s.facts.filter((f) => !shown.has(f.path));
  const max = s.compare ? Math.max(s.compare.baseline.p95, s.compare.variant.p95, 1e-9) * 1.1 : 1;
  const nothing = !s.compare && !s.quantiles.length && !s.facts.length && !s.tables.length && !s.footprints.length;

  // A refused or not-available run: RunMeta already shows the reason as a callout, so show nothing else.
  if (env.status && env.status !== "ok") {
    return (
      <div className="animate-rise-in space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-bold">{title}</h2>
          <KindBadge kind="simulated" text="what-if" />
        </div>
        <p className="hint">Nothing was computed for this run.</p>
        <RunMeta env={env} />
      </div>
    );
  }

  return (
    <div className="animate-rise-in space-y-5">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-bold">{title}</h2>
          <KindBadge kind="simulated" text="what-if" />
        </div>
        {(s.compare?.label ?? env.result.metric) && <p className="hint">Measured as: {s.compare?.label ?? env.result.metric}</p>}
      </div>

      {s.notAvailable && (
        <Callout tone="warn" title="Not available for this run">
          {s.notAvailable}
        </Callout>
      )}

      {s.compare && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Today (baseline)" value={fmtNumber(s.compare.baseline.p50)} unit={unit} note={rangeNote(s.compare.baseline)} />
          <Stat label="With the change" value={fmtNumber(s.compare.variant.p50)} unit={unit} note={rangeNote(s.compare.variant)} tone="whatif" />
        </div>
      )}
      {headline.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {headline.map((q) => (
            <Stat key={q.path} label={q.label} value={q.value} unit={q.unit} note={q.note} />
          ))}
        </div>
      )}

      {s.compare && (
        <Section title={s.compare.label ?? "Baseline and change"}>
          <RangeBar label="Today (baseline)" e={{ ...s.compare.baseline, calibration: env.result.baseline?.calibration }} unit={unit} max={max} note={false} />
          <RangeBar label="With the change (variant)" e={s.compare.variant} unit={unit} max={max} tone="whatif" note={false} />
          <p className="hint">Same scale for both bars. Band = 5th to 95th percentile, line = middle value. Estimates, not measurements.</p>
        </Section>
      )}

      {rest.length > 0 && (
        <Section title="Other figures">
          {/* A bar only says something when there is a spread; single values go in tiles. */}
          {rest.some((q) => q.value.p5 === q.value.p95) && (
            <div className="grid grid-cols-2 gap-2">
              {rest
                .filter((q) => q.value.p5 === q.value.p95)
                .map((q) => (
                  <Stat key={q.path} label={q.label} value={fmtNumber(q.value.p50)} unit={q.unit} note={rangeNote(q.value)} />
                ))}
            </div>
          )}
          {rest
            .filter((q) => q.value.p5 !== q.value.p95)
            .map((q) => (
              <RangeBar key={q.path} label={q.label} e={q.value} unit={q.unit} max={Math.max(q.value.p95, 1e-9) * 1.15} note={false} />
            ))}
        </Section>
      )}
      {!s.compare && s.quantiles.length > 0 && <p className="hint">Estimates, not measurements: read every figure with its range.</p>}

      {s.tables.map((t) => (
        <Section key={t.path} title={`${t.label} (${t.total})`}>
          <div className="overflow-x-auto rounded border border-line">
            <table className="table text-xs">
              <thead>
                <tr>
                  {t.columns.map((c) => (
                    <th key={c} scope="col" className="align-bottom">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td
                        key={j}
                        // Long notes get a readable column width instead of one word per line.
                        className={/^[\d\-—]/.test(c) ? "num whitespace-nowrap" : c.length > 28 ? "min-w-[14rem] break-words" : "break-words"}
                      >
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {t.total > MAX_ROWS && <p className="hint">and {t.total - MAX_ROWS} more</p>}
        </Section>
      ))}

      {facts.length > 0 && (
        <Section title="Details">
          <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-1.5 text-xs">
            {facts.map((f) => (
              <Fragment key={f.path}>
                <dt className="text-muted">{f.label}</dt>
                <dd className={`break-words text-ink ${/^[\d\-]/.test(f.value) ? "num" : ""}`}>{f.value}</dd>
              </Fragment>
            ))}
          </dl>
        </Section>
      )}

      {nothing && !s.notAvailable && <p className="hint">The run returned no figures to show.</p>}

      <div className="border-t border-line pt-3">
        <RunMeta env={env} />
      </div>
    </div>
  );
}

// --- Screen -----------------------------------------------------------------------------------------------

export default function ScenarioLab() {
  const { run } = useSession();
  const { palette } = useTheme();
  const [tile, setTile] = useState<ScenarioTile>("river_flood");
  const [forms, setForms] = useState<Record<ScenarioTile, Form>>(initialForms);
  const [area, setArea] = useState<Area>({ type: "municipio", id: "1" });
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<number[][]>([]);
  const [env, setEnv] = useState<Envelope<ScenarioResult> | null>(null);
  const [ran, setRan] = useState<{ title: string; area: string; tile: ScenarioTile; point: [number, number] | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notLive, setNotLive] = useState(false);
  const [showResult, setShowResult] = useState(false);

  const spec = scenarioSpec(tile);
  const f = forms[tile];
  const kind = resolveKind(tile, f);
  const problem = changeProblem(kind, f);
  const point = placedPoint(tile, f);
  const set = (k: string, v: string) => setForms((all) => ({ ...all, [tile]: { ...all[tile], [k]: v } }));

  async function go() {
    setBusy(true);
    setShowResult(true);
    setError(null);
    setNotLive(false);
    setEnv(null);
    setRan({ title: spec.label, area: areaLabel(area), tile, point });
    try {
      const c = buildScenarioChange(kind, f);
      setEnv(await run<ScenarioResult>("run_scenario", { kind, area: areaToArg(area), change: c }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // The live service lags the engine: a kind it does not know yet is a notice, not a failure.
      if (isUnknownKindError(msg)) setNotLive(true);
      else if (/failed to fetch|networkerror|load failed/i.test(msg))
        setError("The live service did not answer. It may still be starting up, or the run took too long for the connection. Try again: finished runs are kept, so a repeat answers sooner.");
      else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  const onMapClick = (p: { lon: number; lat: number }) => {
    if (drawing) return setDraft((d) => [...d, [p.lon, p.lat]]);
    if (!spec.usesPoint || (tile === "chemical_plume" && f.place === "site")) return;
    setForms((all) => ({ ...all, [tile]: { ...all[tile], lon: p.lon.toFixed(5), lat: p.lat.toFixed(5) } }));
  };

  const summary = useMemo(() => (env ? summariseScenario(env.result) : null), [env]);
  const group = ran ? scenarioSpec(ran.tile).group : spec.group;
  const footColor: Rgb = group === "Water" ? palette.accent : group === "Heat" || group === "Hazard" ? palette.bad : palette.whatIf;

  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (area.type === "polygon" || draft.length) {
      const ring = area.type === "polygon" && !drawing ? area.geometry.coordinates[0]! : draft;
      out.push(
        new PolygonLayer({
          id: "scenario-area",
          data: [{ ring }],
          getPolygon: (d: { ring: number[][] }) => d.ring,
          getFillColor: [...palette.accent, 20],
          getLineColor: [...palette.accent, 255],
          lineWidthMinPixels: 2,
          updateTriggers: { getFillColor: palette.accent, getLineColor: palette.accent },
        }),
        new ScatterplotLayer({
          id: "scenario-area-pts",
          data: drawing ? draft : [],
          getPosition: (p: number[]) => p as [number, number],
          getFillColor: palette.accent,
          radiusMinPixels: 4,
          updateTriggers: { getFillColor: palette.accent },
        }),
      );
    }
    if (summary) {
      // Possible (P95) first, so the likely (P50) footprint sits on top and reads stronger.
      const ordered = [...summary.footprints].sort((a, b) => (a.level === b.level ? 0 : a.level === "possible" ? -1 : 1));
      ordered.forEach((fp, i) => {
        const likely = fp.level === "likely";
        out.push(
          new GeoJsonLayer({
            id: `scenario-footprint-${i}-${fp.path}`,
            data: { type: "Feature", properties: {}, geometry: fp.geometry } as never,
            filled: true,
            stroked: true,
            getFillColor: [...footColor, likely ? 70 : 30],
            getLineColor: [...footColor, likely ? 255 : 150],
            getLineWidth: likely ? 2 : 1,
            lineWidthUnits: "pixels",
            updateTriggers: { getFillColor: footColor, getLineColor: footColor },
          }),
        );
      });
      if (summary.points.length) {
        out.push(
          new ScatterplotLayer({
            id: "scenario-places",
            data: summary.points,
            getPosition: (p: { lon: number; lat: number }) => [p.lon, p.lat],
            getFillColor: palette.point,
            getLineColor: hexRgb(palette.surface),
            stroked: true,
            lineWidthMinPixels: 1.5,
            radiusMinPixels: 4,
            radiusMaxPixels: 6,
            updateTriggers: { getFillColor: palette.point, getLineColor: palette.surface },
          }),
        );
      }
    }
    if (point) {
      out.push(
        new ScatterplotLayer({
          id: "scenario-site-halo",
          data: [point],
          getPosition: (p: [number, number]) => p,
          getFillColor: [...palette.whatIf, 45],
          getLineColor: [...palette.whatIf, 255],
          stroked: true,
          lineWidthMinPixels: 1.5,
          radiusMinPixels: 14,
          radiusMaxPixels: 14,
          updateTriggers: { getFillColor: palette.whatIf, getLineColor: palette.whatIf },
        }),
        new ScatterplotLayer({
          id: "scenario-site",
          data: [point],
          getPosition: (p: [number, number]) => p,
          getFillColor: palette.whatIf,
          radiusMinPixels: 5,
          radiusMaxPixels: 5,
          updateTriggers: { getFillColor: palette.whatIf },
        }),
      );
    }
    return out;
  }, [area, draft, drawing, summary, point, palette, footColor]);

  // Frame the whole result once it arrives (not on every edit): all footprints, else the placed point.
  const focus = useMemo<MapFocus | null>(() => {
    const box = summary ? boundsOf(summary.footprints.map((f) => f.geometry)) : null;
    if (box) return { bounds: box, pitch: 25 };
    const p = summary ? ran?.point : null;
    return p ? { lon: p[0], lat: p[1], zoom: 15 } : null;
  }, [summary, ran]);

  const heavyWarn = isHeavy(kind) && area.type === "city";
  const likelyFp = summary?.footprints.filter((x) => x.level === "likely") ?? [];
  const possibleFp = summary?.footprints.filter((x) => x.level === "possible") ?? [];

  const panel = (
    <Panel
      title="Scenario lab"
      icon={FlaskConical}
      width="w-[24rem]"
      subtitle="Try a change on the city and compare it with today."
      footer={
        <div className="space-y-2">
          <button type="button" className="btn w-full" onClick={() => void go()} disabled={busy || !!problem}>
            {busy ? (
              <>
                <Spinner />
                Running…
              </>
            ) : (
              <>
                <Play className="h-4 w-4" aria-hidden="true" />
                Run scenario
              </>
            )}
          </button>
          <p className="hint" role={problem ? "status" : undefined}>
            {problem ?? "Results compare today (baseline) with your change (variant) and always carry a range."}
          </p>
        </div>
      }
    >
      <Section title="1 · Scenario">
        {/* Groups with one tile share a row, so the whole catalogue fits above the fold. */}
        <div className="grid grid-cols-2 gap-x-1.5 gap-y-2.5">
          {SCENARIO_GROUPS.map((g) => {
            const tiles = SCENARIOS.filter((s) => s.group === g);
            return (
              <div key={g} className={`space-y-1 ${tiles.length > 1 ? "col-span-2" : ""}`} role="group" aria-label={g}>
                <div className="text-2xs font-semibold uppercase tracking-[0.06em] text-muted">{g}</div>
                <div className={`grid gap-1.5 ${tiles.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                  {tiles.map((s) => {
                    const Icon = ICONS[s.id];
                    const active = s.id === tile;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setTile(s.id)}
                        className={`flex h-full flex-col items-start gap-0.5 rounded border px-2 py-1.5 text-left transition-colors duration-150 ${
                          active ? "border-link bg-primary-soft text-link" : "border-line bg-surface text-ink hover:border-line-strong hover:bg-sunken"
                        }`}
                      >
                        <span className="flex items-start gap-1.5 text-sm font-semibold leading-tight">
                          <Icon className="mt-px h-4 w-4 shrink-0" aria-hidden="true" />
                          {s.label}
                        </span>
                        <span className={`text-2xs leading-snug ${active ? "text-ink" : "text-muted"}`}>{s.description}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="2 · Where">
        <AreaPicker area={area} onChange={setArea} drawing={drawing} onDraw={toggleDraw} />
        {heavyWarn && (
          <Callout tone="warn" title="Pick a smaller area">
            This is a heavy simulation: it runs on a municipio, an urban zone or a drawn area. The tool will refuse larger areas.
          </Callout>
        )}
      </Section>

      <Section title="3 · What changes">
        <ChangeForm tile={tile} f={f} set={set} />
      </Section>
    </Panel>
  );

  const right =
    showResult && (busy || env || error || notLive) ? (
      <Panel
        side="right"
        width="w-[24rem]"
        title="Result"
        subtitle={ran ? `${ran.title} · ${ran.area}` : undefined}
        actions={
          <button type="button" className="btn-quiet -mr-1 -mt-0.5" aria-label="Close result" onClick={() => setShowResult(false)}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        }
      >
        {busy && (
          <div className="space-y-4" aria-live="polite">
            <p className="flex items-center gap-2 text-sm text-muted">
              <Spinner />
              Running the scenario…
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div className="skeleton h-16" />
              <div className="skeleton h-16" />
            </div>
            <Skeleton lines={6} />
          </div>
        )}
        {notLive && (
          <Callout tone="warn" title="Not on the live service yet">
            This scenario is built and tested in the engine, but the public service has not been updated to run it, so nothing was computed.
          </Callout>
        )}
        {error && (
          <Callout tone="error" title="The run failed">
            {error}
          </Callout>
        )}
        {env && ran && <ResultView env={env} title={ran.title} />}
      </Panel>
    ) : null;

  return (
    <Workspace panel={panel} right={right}>
      <CityMap layers={layers} initialZoom={12.5} pitch={35} focus={focus} onClick={onMapClick} />

      {!env && !busy && (
        <MapFloat position="top-left" className="max-w-[min(22rem,calc(100%-6rem))]">
          <div role="status" aria-live="polite" className="space-y-0.5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {(() => {
                const Icon = ICONS[tile];
                return <Icon className="h-4 w-4 text-link" aria-hidden="true" />;
              })()}
              {spec.label}
            </div>
            <div className="text-xs text-muted">
              {areaLabel(area)}
              {drawing
                ? " · click the map to add points"
                : spec.usesPoint && !(tile === "chemical_plume" && f.place === "site")
                  ? point
                    ? " · click the map to move the point"
                    : " · click the map to place it"
                  : ""}
            </div>
          </div>
        </MapFloat>
      )}

      {(point || likelyFp.length > 0 || possibleFp.length > 0 || (summary?.points.length ?? 0) > 0) && (
        <MapFloat position="bottom-left" className="w-60">
          <div className="space-y-1.5 text-xs">
            <div className="label">On the map</div>
            {point && (
              <LegendRow swatch={<span className="block h-3 w-3 rotate-45 border-2 border-dashed" style={{ borderColor: rgb(palette.whatIf), background: rgb(palette.whatIf, 0.25) }} />}>
                Your change (what-if)
              </LegendRow>
            )}
            {likelyFp.length > 0 && (
              <LegendRow swatch={<span className="block h-3 w-4 rounded-sm border-2" style={{ borderColor: rgb(footColor), background: rgb(footColor, 0.5) }} />}>
                Likely extent (P50)
              </LegendRow>
            )}
            {possibleFp.length > 0 && (
              <LegendRow swatch={<span className="block h-3 w-4 rounded-sm border" style={{ borderColor: rgb(footColor, 0.6), background: rgb(footColor, 0.16) }} />}>
                Possible extent (P95)
              </LegendRow>
            )}
            {(summary?.points.length ?? 0) > 0 && (
              <LegendRow swatch={<span className="block h-2.5 w-2.5 rounded-full" style={{ background: rgb(palette.point) }} />}>
                Places listed in the result
              </LegendRow>
            )}
            {summary && (likelyFp.length > 0 || possibleFp.length > 0) && <p className="hint">What-if result: an estimate, not a measured event.</p>}
          </div>
        </MapFloat>
      )}

      {env && !showResult && (
        <div className="absolute right-14 top-3 z-10">
          <button type="button" className="btn-ghost btn-sm shadow-float" onClick={() => setShowResult(true)}>
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            Show result
          </button>
        </div>
      )}

    </Workspace>
  );
}

function LegendRow({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex w-4 shrink-0 justify-center" aria-hidden="true">
        {swatch}
      </span>
      <span>{children}</span>
    </div>
  );
}
