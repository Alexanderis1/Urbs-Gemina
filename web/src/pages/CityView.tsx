import { useEffect, useMemo, useState, type ReactNode } from "react";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  AlertTriangle,
  Bike,
  Building2,
  Bus,
  Car,
  CloudRain,
  Hospital,
  Layers as LayersIcon,
  Map as MapIcon,
  RadioTower,
  School,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { CityMap } from "@/map/CityMap";
import { AreaPicker } from "@/components/AreaPicker";
import { RunMeta } from "@/components/RunMeta";
import { KindBadge } from "@/components/Badge";
import { Callout, LegendRamp, MapFloat, Panel, Section, Skeleton, Spinner, Workspace } from "@/components/ui";
import { areaLabel, areaToArg, type Area } from "@/lib/area";
import { ALPHA_FLOOR, confidenceAlpha, rampColor, rampGradient } from "@/lib/colors";
import { onMapAction, registerCityView } from "@/lib/mapbus";
import { areaFromId } from "@/lib/mapActions";
import { isOk } from "@/api/envelope";
import { describeItem, formatValue, normalizeLayer, valueExtent, type MapData, type MapItem } from "@/lib/layers";
import { calibrationLabel } from "@/lib/format";
import { BUILDING_VIEWS, LEGENDS, ROOF_COLORS, type BuildingView } from "@/lib/buildingStyles";
import { useSession } from "@/lib/runlog";
import { useTheme } from "@/lib/useTheme";
import type { Envelope, QueryLayerResult } from "@/api/types";

type LayerGroup = "fields" | "mobility" | "health" | "environment";

// Layer ids as the live query_layer knows them (twin/api). Labels are for people; caveats go in `hint`.
export const MAP_LAYERS: { id: string; label: string; hint?: string; group: LayerGroup; icon: LucideIcon }[] = [
  { id: "antenna_register", label: "Antenna sites", hint: "Count per 500 m cell", group: "fields", icon: RadioTower },
  { id: "emf_baseline", label: "EMF field", hint: "Cartoradio grid", group: "fields", icon: Zap },
  { id: "traffic_flow", label: "Traffic loops", group: "mobility", icon: Car },
  { id: "micromobility", label: "Shared scooters and bikes", group: "mobility", icon: Bike },
  { id: "hospitals", label: "Hospitals", group: "health", icon: Hospital },
  { id: "schools_state", label: "State schools", group: "health", icon: School },
  { id: "rain", label: "Rain", hint: "Fused, with range. Slow: pick a municipio", group: "environment", icon: CloudRain },
  { id: "air_quality", label: "Air quality stations", group: "environment", icon: Wind },
  { id: "air_quality_model", label: "Air quality model", group: "environment", icon: LayersIcon },
  { id: "transit", label: "Transit", hint: "Live buses", group: "mobility", icon: Bus },
];

const GROUPS: { id: LayerGroup; label: string }[] = [
  { id: "fields", label: "Antennas and fields" },
  { id: "mobility", label: "Mobility" },
  { id: "health", label: "Health and schools" },
  { id: "environment", label: "Environment" },
];

const layerLabel = (id: string | null) => MAP_LAYERS.find((l) => l.id === id)?.label ?? "Buildings only";

/** One selectable row. A real radio input (visually hidden) keeps arrow keys and screen readers working. */
function LayerRow({
  label,
  hint,
  icon: Icon,
  checked,
  onSelect,
  badge,
}: {
  label: string;
  hint?: string;
  icon: LucideIcon;
  checked: boolean;
  onSelect: () => void;
  badge?: ReactNode;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-2.5 rounded border px-2.5 py-1.5 transition-colors duration-150 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-link ${
        checked ? "border-link bg-primary-soft" : "border-transparent hover:border-line hover:bg-sunken"
      }`}
    >
      <input type="radio" name="layer" className="sr-only" checked={checked} onChange={onSelect} />
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${checked ? "text-link" : "text-muted"}`} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className={`block text-sm leading-snug ${checked ? "font-semibold text-ink" : "text-ink"}`}>{label}</span>
        {hint && <span className="hint block leading-snug">{hint}</span>}
      </span>
      {badge && <span className="mt-0.5 shrink-0">{badge}</span>}
    </label>
  );
}

/** "#rrggbb" to [r, g, b], for a deck.gl outline in the panel surface colour. */
const hexRgb = (hex: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];

/** Legend title from the data itself: metric, cell size and unit as the tool returned them. */
function legendTitle(d: MapData): string {
  const metric = d.metric.replace(/_/g, " ");
  const cell = d.metric === "count" && d.cellM ? ` per ${formatValue(d.cellM)} m cell` : "";
  const text = `${metric}${cell}${d.unit ? ` (${d.unit})` : ""}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default function CityView() {
  const { run } = useSession();
  const { theme, palette } = useTheme();
  const [layer, setLayer] = useState<string | null>("antenna_register");
  const [area, setArea] = useState<Area>({ type: "city" });
  const [hoursAgo, setHoursAgo] = useState(0);
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [buildingView, setBuildingView] = useState<BuildingView>("plain");
  const [showTrees, setShowTrees] = useState(false);
  const [env, setEnv] = useState<Envelope<QueryLayerResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [radius, setRadius] = useState<{ lon: number; lat: number; radius_m: number } | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; item: MapItem } | null>(null);

  useEffect(() => {
    const off = onMapAction((a) => {
      if (a.tool === "show_layer") setLayer(a.args.visible ? a.args.layer : null);
      else if (a.tool === "show_area") {
        const next = areaFromId(a.args.area);
        if (next) setArea(next);
      } else if (a.tool === "show_radius") setRadius(a.args);
    });
    // Registered after the map's own listener (child effects run first), so replayed fly_to reaches the map.
    const unregister = registerCityView();
    return () => {
      unregister();
      off();
    };
  }, []);

  useEffect(() => {
    setHover(null);
    if (!layer) {
      setBusy(false);
      return setEnv(null);
    }
    if (area.type === "zone" && !area.id) return;
    const time = hoursAgo === 0 ? null : new Date(Date.now() - hoursAgo * 3600_000).toISOString();
    let live = true;
    setError(null);
    setBusy(true);
    run<QueryLayerResult>("query_layer", { layer, area: areaToArg(area), time, limit: 5000 })
      .then((e) => live && setEnv(e))
      .catch((e: unknown) => live && setError(String(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [layer, area, hoursAgo, run]);

  const data = useMemo(() => (env && isOk(env) ? normalizeLayer(env.result) : null), [env]);
  const extent = useMemo(() => (data ? valueExtent(data.items) : null), [data]);
  // Fading only means something when the tool returned an uncertainty for at least one item.
  const hasUncertainty = useMemo(() => !!data?.items.some((i) => i.uncertainty > 0), [data]);

  const layers = useMemo(() => {
    const out: Layer[] = [];
    const accent = palette.accent;
    if (data && data.items.length && extent) {
      const { min: lo, max: hi } = extent;
      const norm = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
      const maxU = Math.max(...data.items.map((i) => (i.value ? i.uncertainty / Math.abs(i.value) : i.uncertainty)), 0);
      const floor = ALPHA_FLOOR[theme];
      const alpha = (i: MapItem) =>
        showUncertainty ? confidenceAlpha(i.value ? i.uncertainty / Math.abs(i.value) : i.uncertainty, maxU, floor) : 200;
      const dark = theme === "dark";
      if (data.kind === "hex") {
        out.push(
          new H3HexagonLayer<MapItem>({
            id: "belief",
            data: data.items,
            getHexagon: (c) => c.h3!,
            getFillColor: (c) => [...rampColor(norm(c.value)), alpha(c)],
            extruded: false,
            // On the dark map a thin edge in the cell's own colour keeps pale, faded cells visible.
            stroked: dark,
            getLineColor: (c) => [...rampColor(norm(c.value)), 150],
            lineWidthUnits: "pixels",
            getLineWidth: 1,
            pickable: true,
            updateTriggers: { getFillColor: [showUncertainty, lo, hi, maxU, theme], getLineColor: [lo, hi] },
          }),
        );
      } else {
        const sized = data.metric === "count";
        const site = data.metric === "site";
        out.push(
          new ScatterplotLayer<MapItem>({
            id: "points",
            data: data.items,
            getPosition: (i) => i.position!,
            getFillColor: (i) => (site ? [...palette.point, 220] : [...rampColor(norm(i.value)), alpha(i)]),
            getRadius: (i) => (sized ? Math.sqrt(i.value) * 70 : 40),
            radiusUnits: "meters",
            radiusMinPixels: site ? 4 : 3,
            stroked: true,
            getLineColor: (i) => (i.synthetic ? [...palette.simulated, 255] : site ? [...hexRgb(palette.surface), 230] : [...palette.inactive, dark ? 220 : 120]),
            lineWidthMinPixels: 1,
            getLineWidth: (i) => (i.synthetic ? 2 : 1),
            lineWidthUnits: "pixels",
            pickable: true,
            updateTriggers: {
              getFillColor: [showUncertainty, lo, hi, maxU, theme],
              getLineColor: [theme],
            },
          }),
        );
      }
    }
    if (radius) {
      out.push(
        new ScatterplotLayer({
          id: "radius",
          data: [radius],
          getPosition: (r: { lon: number; lat: number }) => [r.lon, r.lat],
          getRadius: radius.radius_m,
          radiusUnits: "meters",
          stroked: true,
          getFillColor: [...accent, 30],
          getLineColor: [...accent, 255],
          lineWidthMinPixels: 2,
          updateTriggers: { getFillColor: [theme], getLineColor: [theme] },
        }),
      );
    }
    if (area.type === "polygon" || draft.length) {
      const ring = area.type === "polygon" && !drawing ? area.geometry.coordinates[0]! : draft;
      out.push(
        new PolygonLayer({
          id: "area",
          data: [{ ring }],
          getPolygon: (d: { ring: number[][] }) => d.ring,
          getFillColor: [...accent, 25],
          getLineColor: [...accent, 255],
          lineWidthMinPixels: 2,
          updateTriggers: { getFillColor: [theme], getLineColor: [theme] },
        }),
        new ScatterplotLayer({
          id: "area-pts",
          data: drawing ? draft : [],
          getPosition: (p: [number, number]) => p,
          getFillColor: [...accent, 255],
          radiusMinPixels: 4,
          updateTriggers: { getFillColor: [theme] },
        }),
      );
    }
    return out;
  }, [data, extent, showUncertainty, area, draft, drawing, radius, theme, palette]);

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  const onHover = (info: PickingInfo) => {
    const id = info.layer?.id;
    if (info.object && (id === "belief" || id === "points")) setHover({ x: info.x, y: info.y, item: info.object as MapItem });
    else setHover(null);
  };

  const kind = layer && env ? env.data_kinds[layer] : undefined;
  const empty = data && !busy && data.items.length === 0;
  const unit = data?.unit ? ` ${data.unit}` : "";
  const hovered = hover && data ? describeItem(hover.item, data) : null;

  const panel = (
    <Panel title="City view" icon={MapIcon} subtitle="Pick one layer and an area to see what the twin knows about it.">
      <Section title="Layer">
        <div role="radiogroup" aria-label="Map layer" className="space-y-3">
          {GROUPS.map((g) => (
            <div key={g.id} className="space-y-0.5">
              <div className="px-1 text-2xs font-semibold text-muted">{g.label}</div>
              {MAP_LAYERS.filter((l) => l.group === g.id).map((l) => (
                <LayerRow
                  key={l.id}
                  label={l.label}
                  hint={l.hint}
                  icon={l.icon}
                  checked={layer === l.id}
                  onSelect={() => setLayer(l.id)}
                  badge={layer === l.id && kind ? <KindBadge kind={kind} /> : undefined}
                />
              ))}
            </div>
          ))}
          <LayerRow label="None (buildings only)" icon={Building2} checked={layer === null} onSelect={() => setLayer(null)} />
        </div>
      </Section>

      <Section title="Where">
        <AreaPicker area={area} onChange={setArea} drawing={drawing} onDraw={toggleDraw} />
      </Section>

      <Section title="When">
        <input
          type="range"
          min={0}
          max={24}
          value={24 - hoursAgo}
          onChange={(e) => setHoursAgo(24 - Number(e.target.value))}
          className="w-full"
          aria-label="Time, hours before now"
          aria-valuetext={hoursAgo === 0 ? "Now" : `${hoursAgo} hours ago`}
        />
        <div className="flex justify-between text-2xs text-muted">
          <span>24 h ago</span>
          <span>Now</span>
        </div>
        <p className="text-sm">
          Showing: <span className="font-semibold">{hoursAgo === 0 ? "now (latest data)" : `${hoursAgo} ${hoursAgo === 1 ? "hour" : "hours"} ago`}</span>
        </p>
      </Section>

      <Section title="Display" collapsible>
        <div>
          <label className="check">
            <input type="checkbox" checked={showUncertainty} onChange={(e) => setShowUncertainty(e.target.checked)} />
            Show uncertainty
          </label>
          <p className="hint ml-6">Less certain values are drawn fainter.</p>
        </div>
        <label className="block space-y-1">
          <span className="block text-xs font-semibold text-ink">Buildings</span>
          <select className="input" value={buildingView} onChange={(e) => setBuildingView(e.target.value as BuildingView)}>
            {BUILDING_VIEWS.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        {buildingView !== "plain" && <KindBadge kind="estimated" />}
        {(buildingView === "height_sd" || buildingView === "insar") && (
          <LegendRamp gradient={LEGENDS[buildingView].gradient} low={LEGENDS[buildingView].low} high={LEGENDS[buildingView].high} />
        )}
        {buildingView === "roof" && (
          <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs">
            {Object.entries(ROOF_COLORS).map(([k, c]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-line-strong" style={{ background: c }} aria-hidden="true" />
                {k.replace(/_/g, " ")}
              </span>
            ))}
            <span className="hint col-span-2">Centre district only.</span>
          </div>
        )}
        <label className="check">
          <input type="checkbox" checked={showTrees} onChange={(e) => setShowTrees(e.target.checked)} />
          Trees (zoom in to see them)
        </label>
      </Section>

      <Section title="Evidence" collapsible>
        {error && (
          <Callout tone="error" title="The layer could not be loaded">
            {error}
          </Callout>
        )}
        {env ? (
          <RunMeta env={env} />
        ) : busy ? (
          <Skeleton lines={2} />
        ) : (
          !error && <p className="hint">The record of the tool run appears here once a layer is loaded.</p>
        )}
      </Section>
    </Panel>
  );

  return (
    <Workspace panel={panel}>
      <CityMap
        layers={layers}
        buildingView={buildingView}
        showTrees={showTrees}
        onHover={onHover}
        onClick={drawing ? (p) => setDraft((d) => [...d, [p.lon, p.lat]]) : undefined}
      />

      <MapFloat position="top-left" className="max-w-[min(22rem,calc(100%-6rem))]">
        <div role="status" aria-live="polite" className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{layerLabel(layer)}</span>
            {layer && kind && !busy && <KindBadge kind={kind} />}
          </div>
          <div className="text-xs text-muted">
            {!layer ? (
              "No data layer selected"
            ) : busy ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3.5 w-3.5" />
                Loading layer…
              </span>
            ) : error ? (
              <span className="text-danger">Could not load this layer. See Evidence.</span>
            ) : empty ? (
              <span className="inline-flex items-center gap-1.5 text-estimated">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                No data in this area right now
              </span>
            ) : data ? (
              <span>
                <span className="num text-ink">{data.items.length.toLocaleString("en-GB")}</span> {data.kind === "hex" ? "cells" : "points"} ·{" "}
                {areaLabel(area)}
                {data.truncated && data.count ? ` (first ${data.items.length.toLocaleString("en-GB")} of ${data.count.toLocaleString("en-GB")})` : ""}
              </span>
            ) : null}
          </div>
        </div>
      </MapFloat>

      {layer && data && extent && data.items.length > 0 && (
        <MapFloat position="bottom-left" className={data.metric === "site" ? "" : "w-64"}>
          {data.metric === "site" ? (
            <div className="flex items-center gap-2 text-xs">
              <span
                className="inline-block h-3 w-3 rounded-full border border-surface"
                style={{ background: `rgb(${palette.point.join(" ")})` }}
                aria-hidden="true"
              />
              One dot per site
            </div>
          ) : (
            <div className="space-y-1.5">
              <div className="text-xs font-semibold text-ink">{legendTitle(data)}</div>
              <LegendRamp
                gradient={rampGradient()}
                low={`${formatValue(extent.min)}${unit}`}
                high={`${formatValue(extent.max)}${unit}`}
              />
              {data.metric === "count" && <p className="hint">Bigger dot = more sites.</p>}
              {showUncertainty && hasUncertainty && <p className="hint">Faded = less certain</p>}
              {data.calibration && (data.calibration === "calibrated" || data.calibration === "uncalibrated") && (
                <p className="hint">{calibrationLabel(data.calibration)}</p>
              )}
              {data.items.some((i) => i.synthetic) && (
                <p className="flex items-center gap-1.5 text-2xs text-muted">
                  <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-dashed border-simulated" aria-hidden="true" />
                  Outlined = simulated
                </p>
              )}
            </div>
          )}
        </MapFloat>
      )}

      {hover && hovered && (hovered.title || hovered.lines.length > 0) && (
        <div
          className="map-float pointer-events-none absolute z-20 max-w-xs px-2.5 py-1.5 text-xs"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
          role="tooltip"
        >
          {hovered.title && <div className="font-semibold text-ink">{hovered.title}</div>}
          {hovered.lines.map((l, i) => (
            <div key={l} className={i === 0 ? "font-semibold text-ink" : "text-muted"}>
              {l}
            </div>
          ))}
          {hovered.synthetic && (
            <div className="mt-1">
              <KindBadge kind="simulated" />
            </div>
          )}
        </div>
      )}
    </Workspace>
  );
}
