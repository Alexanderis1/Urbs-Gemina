import { useEffect, useMemo, useState } from "react";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { CityMap } from "@/map/CityMap";
import { AreaPicker } from "@/components/AreaPicker";
import { RunMeta } from "@/components/RunMeta";
import { areaToArg, type Area } from "@/lib/area";
import { confidenceAlpha, rampColor } from "@/lib/colors";
import { onMapAction, registerCityView } from "@/lib/mapbus";
import { isOk } from "@/api/envelope";
import { areaFromId } from "@/lib/mapActions";
import { useSession } from "@/lib/runlog";
import type { Envelope, LayerCell, QueryLayerResult } from "@/api/types";

// Belief layers from the design (section 9). Ids are provisional until WS4/WS5 publish the query_layer schema.
export const BELIEF_LAYERS = [
  { id: "air_quality", label: "Air quality" },
  { id: "transit_delay", label: "Transit delay" },
  { id: "road_speed", label: "Road speed" },
  { id: "rain", label: "Rain" },
  { id: "emf", label: "EMF field" },
  { id: "activity", label: "Activity" },
];

export default function CityView() {
  const { run } = useSession();
  const [layer, setLayer] = useState<string | null>("air_quality");
  const [area, setArea] = useState<Area>({ type: "city" });
  const [hoursAgo, setHoursAgo] = useState(0);
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [env, setEnv] = useState<Envelope<QueryLayerResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [radius, setRadius] = useState<{ lon: number; lat: number; radius_m: number } | null>(null);

  useEffect(() => {
    const off = onMapAction((a) => {
      if (a.tool === "show_layer") {
        if (BELIEF_LAYERS.some((l) => l.id === a.args.layer)) setLayer(a.args.visible ? a.args.layer : null);
      } else if (a.tool === "show_area") {
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
    const time = new Date(Date.now() - hoursAgo * 3600_000).toISOString();
    let live = true;
    setError(null);
    run<QueryLayerResult>("query_layer", { layer, area: areaToArg(area), time })
      .then((e) => live && setEnv(e))
      .catch((e: unknown) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [layer, area, hoursAgo, run]);

  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (env && isOk(env)) {
      const cells = env.result.cells;
      const maxMean = Math.max(...cells.map((c) => c.mean), 1e-9);
      const maxVar = Math.max(...cells.map((c) => c.variance), 0);
      out.push(
        new H3HexagonLayer<LayerCell>({
          id: "belief",
          data: cells,
          getHexagon: (c) => c.h3,
          getFillColor: (c) => [...rampColor(c.mean / maxMean), showUncertainty ? confidenceAlpha(c.variance, maxVar) : 190],
          extruded: false,
          stroked: false,
          pickable: true,
          updateTriggers: { getFillColor: [showUncertainty, maxMean, maxVar] },
        }),
      );
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
  }, [env, showUncertainty, area, draft, drawing, radius]);

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  return (
    <div className="flex h-full">
      <aside className="w-72 shrink-0 space-y-4 overflow-y-auto border-r border-stone-200 bg-white p-4">
        <div className="space-y-1">
          <div className="label">Layer</div>
          {BELIEF_LAYERS.map((l) => (
            <label key={l.id} className="flex items-center gap-2 text-sm">
              <input type="radio" name="layer" checked={layer === l.id} onChange={() => setLayer(l.id)} />
              {l.label}
            </label>
          ))}
          <label className="flex items-center gap-2 text-sm">
            <input type="radio" name="layer" checked={layer === null} onChange={() => setLayer(null)} />
            Buildings only
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
            <div className="label">Legend</div>
            <div className="h-2 rounded" style={{ background: "linear-gradient(90deg,#fff5dc,#fdcc8a,#fc8d59,#d7301f,#7f0000)" }} />
            <div className="flex justify-between text-xs text-stone-500">
              <span>low</span>
              <span>{env?.result.unit}</span>
              <span>high</span>
            </div>
          </div>
        )}
        {error && <p className="text-sm text-red-700">{error}</p>}
        {env && <RunMeta env={env} />}
      </aside>
      <div className="relative flex-1">
        <CityMap layers={layers} onClick={drawing ? (p) => setDraft((d) => [...d, [p.lon, p.lat]]) : undefined} />
      </div>
    </div>
  );
}
