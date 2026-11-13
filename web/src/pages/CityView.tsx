import { useEffect, useMemo, useState } from "react";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { CityMap } from "@/map/CityMap";
import { AreaPicker } from "@/components/AreaPicker";
import { RunMeta } from "@/components/RunMeta";
import { KindBadge } from "@/components/Badge";
import { areaToArg, type Area } from "@/lib/area";
import { confidenceAlpha, rampColor } from "@/lib/colors";
import { onMapAction, registerCityView } from "@/lib/mapbus";
import { areaFromId } from "@/lib/mapActions";
import { isOk } from "@/api/envelope";
import { normalizeLayer, type MapItem } from "@/lib/layers";
import { BUILDING_VIEWS, LEGENDS, ROOF_COLORS, type BuildingView } from "@/lib/buildingStyles";
import { useSession } from "@/lib/runlog";
import type { Envelope, QueryLayerResult } from "@/api/types";

// Layer ids as the live query_layer knows them (twin/api). Labels are for people.
export const MAP_LAYERS = [
  { id: "antenna_register", label: "Antenna sites (per 500 m cell)" },
  { id: "emf_baseline", label: "EMF field (Cartoradio)" },
  { id: "traffic_flow", label: "Traffic loops" },
  { id: "micromobility", label: "Shared scooters and bikes" },
  { id: "hospitals", label: "Hospitals" },
  { id: "schools_state", label: "State schools" },
  { id: "rain", label: "Rain (fused, with range; slow, pick a municipio)" },
  { id: "air_quality", label: "Air quality stations" },
  { id: "air_quality_model", label: "Air quality model" },
  { id: "transit", label: "Transit (live buses)" },
];

export default function CityView() {
  const { run } = useSession();
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
    if (!layer) return setEnv(null);
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

  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (data && data.items.length) {
      const vals = data.items.map((i) => i.value);
      const lo = Math.min(...vals);
      const hi = Math.max(...vals);
      const norm = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
      const maxU = Math.max(...data.items.map((i) => (i.value ? i.uncertainty / Math.abs(i.value) : i.uncertainty)), 0);
      const alpha = (i: MapItem) =>
        showUncertainty ? confidenceAlpha(i.value ? i.uncertainty / Math.abs(i.value) : i.uncertainty, maxU) : 200;
      if (data.kind === "hex") {
        out.push(
          new H3HexagonLayer<MapItem>({
            id: "belief",
            data: data.items,
            getHexagon: (c) => c.h3!,
            getFillColor: (c) => [...rampColor(norm(c.value)), alpha(c)],
            extruded: false,
            stroked: false,
            pickable: true,
            updateTriggers: { getFillColor: [showUncertainty, lo, hi, maxU] },
          }),
        );
      } else {
        const sized = data.metric === "count";
        out.push(
          new ScatterplotLayer<MapItem>({
            id: "points",
            data: data.items,
            getPosition: (i) => i.position!,
            getFillColor: (i) => (data.metric === "site" ? [37, 99, 235, 220] : [...rampColor(norm(i.value)), alpha(i)]),
            getRadius: (i) => (sized ? Math.sqrt(i.value) * 70 : 40),
            radiusUnits: "meters",
            radiusMinPixels: 3,
            stroked: true,
            getLineColor: (i) => (i.synthetic ? [124, 58, 237, 255] : [40, 40, 40, 120]),
            lineWidthMinPixels: 1,
            pickable: true,
            updateTriggers: { getFillColor: [showUncertainty, lo, hi, maxU] },
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
          getFillColor: [139, 30, 45, 30],
          getLineColor: [139, 30, 45, 255],
          lineWidthMinPixels: 2,
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
          getFillColor: [139, 30, 45, 25],
          getLineColor: [139, 30, 45, 255],
          lineWidthMinPixels: 2,
        }),
        new ScatterplotLayer({
          id: "area-pts",
          data: drawing ? draft : [],
          getPosition: (p: [number, number]) => p,
          getFillColor: [139, 30, 45],
          radiusMinPixels: 4,
        }),
      );
    }
    return out;
  }, [data, showUncertainty, area, draft, drawing, radius]);

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  const kind = layer && env ? env.data_kinds[layer] : undefined;

  return (
    <div className="flex h-full">
      <aside className="w-72 shrink-0 space-y-4 overflow-y-auto border-r border-stone-200 bg-white p-4">
        <div className="space-y-1">
          <div className="label">Layer</div>
          {MAP_LAYERS.map((l) => (
            <label key={l.id} className="flex items-center gap-2 text-sm">
              <input type="radio" name="layer" checked={layer === l.id} onChange={() => setLayer(l.id)} />
              {l.label}
            </label>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="layer" checked={layer === null} onChange={() => setLayer(null)} />
            None (buildings only)
          </label>
        </div>
        <AreaPicker area={area} onChange={setArea} drawing={drawing} onDraw={toggleDraw} />
        <div className="space-y-1">
          <div className="label">Time</div>
          <input
            type="range"
            min={0}
            max={24}
            value={24 - hoursAgo}
            onChange={(e) => setHoursAgo(24 - Number(e.target.value))}
            className="w-full accent-roma"
          />
          <div className="text-xs text-stone-500">{hoursAgo === 0 ? "Now" : `${hoursAgo} h ago`}</div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showUncertainty} onChange={(e) => setShowUncertainty(e.target.checked)} />
          Show uncertainty (faded = less certain)
        </label>
        {layer && (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="label">Legend</span>
              {kind && <KindBadge kind={kind} />}
            </div>
            <div className="h-2 rounded" style={{ background: "linear-gradient(90deg,#fff5dc,#fdcc8a,#fc8d59,#d7301f,#7f0000)" }} />
            <div className="flex justify-between text-xs text-stone-500">
              <span>low</span>
              <span>
                {data?.metric}
                {data?.unit ? ` (${data.unit})` : ""}
              </span>
              <span>high</span>
            </div>
            {busy && <p className="text-xs text-stone-500">Loading…</p>}
            {data && !busy && (
              <p className="text-xs text-stone-500">
                {data.items.length} {data.kind === "hex" ? "cells" : "points"} shown
                {data.truncated ? ` (first ${data.items.length} of ${data.count})` : ""}
                {data.calibration ? ` · ${data.calibration}` : ""}
              </p>
            )}
            {data && !busy && data.items.length === 0 && <p className="text-xs text-amber-700">No data in this area right now.</p>}
          </div>
        )}
        <div className="space-y-1 border-t border-stone-200 pt-3">
          <div className="label">Buildings</div>
          <select className="input" value={buildingView} onChange={(e) => setBuildingView(e.target.value as BuildingView)}>
            {BUILDING_VIEWS.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
          {buildingView !== "plain" && <KindBadge kind="estimated" />}
          {(buildingView === "height_sd" || buildingView === "insar") && (
            <div>
              <div className="h-2 rounded" style={{ background: LEGENDS[buildingView].gradient }} />
              <div className="flex justify-between text-xs text-stone-500">
                <span>{LEGENDS[buildingView].low}</span>
                <span>{LEGENDS[buildingView].high}</span>
              </div>
            </div>
          )}
          {buildingView === "roof" && (
            <div className="grid grid-cols-2 gap-1 text-xs">
              {Object.entries(ROOF_COLORS).map(([k, c]) => (
                <span key={k} className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-sm" style={{ background: c }} /> {k.replace(/_/g, " ")}
                </span>
              ))}
              <span className="col-span-2 text-stone-500">Centre district only.</span>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={showTrees} onChange={(e) => setShowTrees(e.target.checked)} />
            Trees (zoom in)
          </label>
        </div>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {env && <RunMeta env={env} />}
      </aside>
      <div className="relative flex-1">
        <CityMap
          layers={layers}
          buildingView={buildingView}
          showTrees={showTrees}
          onClick={drawing ? (p) => setDraft((d) => [...d, [p.lon, p.lat]]) : undefined}
        />
      </div>
    </div>
  );
}
