import { useEffect, useMemo, useState, type ReactNode } from "react";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { AlertTriangle, Building2, Map as MapIcon, type LucideIcon } from "lucide-react";
import { CityMap, type MapFocus } from "@/map/CityMap";
import { AreaPicker } from "@/components/AreaPicker";
import { RunMeta } from "@/components/RunMeta";
import { ResourceDetail, ResourceHover } from "@/components/MarkerCard";
import { markerLayers, pickedMarker, type Marker } from "@/map/markers";
import { describeResource, layerGlyph } from "@/lib/resource";
import { TWIN_START_ZOOM } from "@/lib/twinOverlay";
import { KindBadge } from "@/components/Badge";
import { Callout, Field, LegendRamp, MapFloat, Panel, Section, Skeleton, Spinner, Workspace } from "@/components/ui";
import { areaLabel, areaToArg, type Area } from "@/lib/area";
import { ALPHA_FLOOR, areaAlpha, confidenceAlpha, rampColor, rampGradient } from "@/lib/colors";
import { onMapAction, registerCityView } from "@/lib/mapbus";
import { areaFromId } from "@/lib/mapActions";
import { isOk } from "@/api/envelope";
import {
  areaBounds,
  areaForLayer,
  availableMetrics,
  firstSentence,
  formatValue,
  metricInfo,
  MAX_VALUE_LABELS,
  normalizeLayer,
  pointStyle,
  valueExtent,
  type MapData,
  type MapItem,
} from "@/lib/layers";
import { calibrationLabel } from "@/lib/format";
import { BUILDING_VIEWS, LEGENDS, ROOF_COLORS, roofLabel, type BuildingView } from "@/lib/buildingStyles";
import { useSession } from "@/lib/runlog";
import { useTheme } from "@/lib/useTheme";
import { GROUPS, isFused, layerLabel, layersFor } from "@/lib/layerCatalogue";
import type { Experience } from "@/lib/tiers";
import type { Envelope, QueryLayerResult } from "@/api/types";
import { errorText } from "@/lib/errors";
import { locale, texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    cellsWord: "cells",
    pointsWord: "points",
    perCell: (n: string) => ` per ${n} m cell`,
    noData: "The twin has no data for this layer yet.",
    cityView: "City view",
    cityMap: "City map",
    subStaff: "Pick one layer and an area to see what the twin knows about it.",
    subPublic: "Pick what you want to see, and where. Each map says how sure it is.",
    layerStaff: "Layer",
    layerPublic: "Show on the map",
    mapLayer: "Map layer",
    none: "None (buildings only)",
    where: "Where",
    partOfCity: "Part of the city",
    when: "When",
    timeAria: "Time, hours before now",
    now: "Now",
    hoursAgo: (h: number) => `${h} hours ago`,
    ago24: "24 h ago",
    showing: "Showing:",
    nowLatest: "now (latest data)",
    hoursAgoShown: (h: number) => `${h} ${h === 1 ? "hour" : "hours"} ago`,
    display: "Display",
    showUncertainty: "Show uncertainty",
    lessCertain: "Less certain values are drawn fainter.",
    buildings: "Buildings",
    centreOnly: "Centre district only.",
    trees: "Trees (zoom in to see them)",
    evidenceStaff: "Evidence",
    evidencePublic: "How we know this",
    loadError: "The layer could not be loaded",
    runRecord: "The record of the tool run appears here once a layer is loaded.",
    noLayer: "No data layer selected",
    loading: "Loading layer…",
    errStaff: "Could not load this layer. See Evidence.",
    errPublic: (e: string) => `This could not be loaded right now. ${e}`,
    emptyArea: "No data in this area right now",
    incomplete: (shown: string, total: string, things: string) =>
      `Thinned view: ${shown} of ${total} ${things}, picked evenly across the area. Pick a municipio, an urban zone or draw an area to see them all.`,
    onePer: "One marker per",
    site: "site",
    record: "record",
    valueShown: "Value shown",
    sameEverywhere: "Same value everywhere:",
    biggerDot: "Taller column = more sites.",
    faded: "Faded = less certain",
    outlined: "Purple outline = simulated",
  },
  it: {
    cellsWord: "celle",
    pointsWord: "punti",
    perCell: (n: string) => ` per cella di ${n} m`,
    noData: "Il gemello non ha ancora dati per questo livello.",
    cityView: "Vista città",
    cityMap: "Mappa della città",
    subStaff: "Scegli un livello e un'area per vedere cosa sa il gemello.",
    subPublic: "Scegli cosa vuoi vedere e dove. Ogni mappa dice quanto è affidabile.",
    layerStaff: "Livello",
    layerPublic: "Mostra sulla mappa",
    mapLayer: "Livello della mappa",
    none: "Nessuno (solo edifici)",
    where: "Dove",
    partOfCity: "Parte della città",
    when: "Quando",
    timeAria: "Orario, ore prima di adesso",
    now: "Adesso",
    hoursAgo: (h: number) => `${h} ore fa`,
    ago24: "24 h fa",
    showing: "Stai vedendo:",
    nowLatest: "adesso (dati più recenti)",
    hoursAgoShown: (h: number) => `${h} ${h === 1 ? "ora" : "ore"} fa`,
    display: "Visualizzazione",
    showUncertainty: "Mostra l'incertezza",
    lessCertain: "I valori meno certi sono disegnati più sbiaditi.",
    buildings: "Edifici",
    centreOnly: "Solo il centro.",
    trees: "Alberi (ingrandisci per vederli)",
    evidenceStaff: "Evidenze",
    evidencePublic: "Come lo sappiamo",
    loadError: "Non è stato possibile caricare il livello",
    runRecord: "Il registro dell'esecuzione dello strumento compare qui dopo il caricamento di un livello.",
    noLayer: "Nessun livello di dati selezionato",
    loading: "Caricamento del livello…",
    errStaff: "Non è stato possibile caricare questo livello. Vedi Evidenze.",
    errPublic: (e: string) => `Al momento non è stato possibile caricarlo. ${e}`,
    emptyArea: "Nessun dato in quest'area adesso",
    incomplete: (shown: string, total: string, things: string) =>
      `Vista ridotta: ${shown} di ${total} ${things}, scelti in modo uniforme nell'area. Scegli un municipio, una zona urbanistica o disegna un'area per vederli tutti.`,
    onePer: "Un segnaposto per",
    site: "sito",
    record: "record",
    valueShown: "Valore mostrato",
    sameEverywhere: "Stesso valore ovunque:",
    biggerDot: "Colonna più alta = più siti.",
    faded: "Sbiadito = meno certo",
    outlined: "Contorno viola = simulato",
  },
});

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
      className={`relative flex cursor-pointer items-start gap-2.5 rounded border px-2.5 py-1.5 transition-colors duration-150 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-link ${
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

/** Legend title from the data itself: the value's plain name, cell size and unit. */
function legendTitle(d: MapData): string {
  const t = tr(T);
  if (d.kind === "hex") return `${metricInfo(d.metric).label}${d.unit ? ` (${d.unit})` : ""}`;
  const cell = d.metric === "count" && d.cellM ? t.perCell(formatValue(d.cellM)) : "";
  return `${metricInfo(d.metric).label}${cell}${d.unit ? ` (${d.unit})` : ""}`;
}

/**
 * The map of Rome with one data layer on it. Staff get the full console (every layer, drawing, time, display
 * options, evidence open); residents get a short list in plain words and the evidence folded away.
 */
export default function CityView({ audience = "staff" }: { audience?: Experience }) {
  const t = tr(T);
  const staff = audience === "staff";
  const catalogue = layersFor(audience);
  const { run } = useSession();
  const { theme, palette } = useTheme();
  // Opens on a fused layer over the centre: it answers fast and shows the twin doing its job.
  const [layer, setLayer] = useState<string | null>("air_no2");
  const [area, setArea] = useState<Area>(() => areaForLayer(true, { type: "city" }));
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
  const [hover, setHover] = useState<{ x: number; y: number; item: MapItem; id?: string } | null>(null);
  /** The thing whose detail card is open (after a click or tap). */
  const [selected, setSelected] = useState<{ item: MapItem; id?: string } | null>(null);
  const [zoom, setZoom] = useState<number>(TWIN_START_ZOOM);
  const [camera, setCamera] = useState<MapFocus | null>(null);
  /** The value shown, for layers whose sensors report several. Null = the usual one. */
  const [metric, setMetric] = useState<string | null>(null);
  useEffect(() => setMetric(null), [layer]);

  /** A fused layer picked on the whole city opens on the centre: see areaForLayer. */
  const pickLayer = (id: string | null) => {
    setLayer(id);
    setArea((a) => areaForLayer(isFused(id), a));
  };

  useEffect(() => {
    const off = onMapAction((a) => {
      if (a.tool === "show_layer") {
        const id = a.args.visible ? a.args.layer : null;
        setLayer(id);
        setArea((prev) => areaForLayer(isFused(id), prev));
      }
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
    setSelected(null);
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
      .catch((e: unknown) => live && setError(errorText(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [layer, area, hoursAgo, run]);

  // Sensors that report several values (NO₂, PM10, PM2.5): the operator picks which one is shown.
  const metrics = useMemo(() => (env && isOk(env) ? availableMetrics(env.result) : []), [env]);
  const data = useMemo(() => (env && isOk(env) ? normalizeLayer(env.result, metric ?? undefined) : null), [env, metric]);
  // The camera frames the municipio, zone or drawn area the answer is for. Keyed on the box, so a reload does not move it again.
  const boundsKey = env && isOk(env) ? JSON.stringify(areaBounds(env.result)) : "null";
  useEffect(() => {
    const bounds = JSON.parse(boundsKey) as ReturnType<typeof areaBounds>;
    setCamera(bounds ? { bounds, pitch: 45 } : null);
  }, [boundsKey]);
  const extent = useMemo(() => (data ? valueExtent(data.items) : null), [data]);
  // Fading only means something when the tool returned an uncertainty for at least one item.
  const hasUncertainty = useMemo(() => !!data?.items.some((i) => i.uncertainty > 0), [data]);

  // Points become 3D markers on the city model: a column from the exact spot, a badge or the value on top.
  const markers = useMemo<Marker<MapItem>[]>(() => {
    if (!data || data.kind !== "points" || !extent) return [];
    const { min: lo, max: hi } = extent;
    const norm = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
    const style = pointStyle(data);
    const glyph = layerGlyph(layer);
    // A handful of readings: write each value on its column, so nobody has to hover to read the city.
    const written = style !== "sites" && data.items.length <= MAX_VALUE_LABELS;
    return data.items.map((i, n) => ({
      id: i.id ?? String(n),
      position: i.position!,
      color: style === "sites" ? palette.point : rampColor(norm(i.value)),
      level: style === "sites" ? null : norm(i.value),
      ...(written ? { text: formatValue(i.value) } : { glyph }),
      synthetic: i.synthetic,
      data: i,
    }));
  }, [data, extent, layer, palette]);

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
      if (data.kind === "hex") {
        out.push(
          new H3HexagonLayer<MapItem>({
            id: "belief",
            data: data.items,
            getHexagon: (c) => c.h3!,
            // See-through, so the 3D buildings under each cell stay readable.
            getFillColor: (c) => [...rampColor(norm(c.value)), areaAlpha(alpha(c))],
            extruded: false,
            // A thin edge in the cell's own colour keeps pale, faded cells visible over the buildings.
            stroked: true,
            getLineColor: (c) => [...rampColor(norm(c.value)), 150],
            lineWidthUnits: "pixels",
            getLineWidth: 1,
            pickable: true,
            updateTriggers: { getFillColor: [showUncertainty, lo, hi, maxU, theme], getLineColor: [lo, hi] },
          }),
        );
      }
    }
    out.push(...markerLayers(markers, { id: "pts", zoom, palette, selectedId: selected?.id, hoveredId: hover?.id }));
    if (data?.kind === "hex" && selected?.item.h3) {
      out.push(
        new H3HexagonLayer<MapItem>({
          id: "belief-selected",
          data: [selected.item],
          getHexagon: (c) => c.h3!,
          filled: false,
          extruded: false,
          stroked: true,
          getLineColor: [...accent, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 3,
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
  }, [data, extent, markers, zoom, selected, hover?.id, showUncertainty, area, draft, drawing, radius, theme, palette]);

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  const onHover = (info: PickingInfo) => {
    const marker = pickedMarker<MapItem>(info, "pts");
    if (marker) setHover({ x: info.x, y: info.y, item: marker.data, id: marker.id });
    else if (info.object && info.layer?.id === "belief") setHover({ x: info.x, y: info.y, item: info.object as MapItem });
    else setHover(null);
  };
  const onPick = (info: PickingInfo) => {
    // While drawing an area every click is a corner of it, also over a cell or a marker.
    if (drawing) return false;
    const marker = pickedMarker<MapItem>(info, "pts");
    if (marker) setSelected({ item: marker.data, id: marker.id });
    else if (info.object && info.layer?.id === "belief") setSelected({ item: info.object as MapItem });
    else setSelected(null);
    setHover(null);
  };

  const kind = layer && env ? env.data_kinds[layer] : undefined;
  const empty = data && !busy && data.items.length === 0;
  // The tool answered, but not with data (a layer the live service does not carry yet): say so in its own words.
  const refusal = env && !isOk(env) ? firstSentence(env.reason ?? t.noData) : null;
  const things = data?.kind === "hex" ? t.cellsWord : t.pointsWord;
  const unit = data?.unit ? ` ${data.unit}` : "";
  const hovered = hover && data ? describeResource(hover.item, data, layer) : null;
  const detail = selected && data ? describeResource(selected.item, data, layer) : null;

  const panel = (
    <Panel
      title={staff ? t.cityView : t.cityMap}
      icon={MapIcon}
      subtitle={staff ? t.subStaff : t.subPublic}
    >
      <Section title={staff ? t.layerStaff : t.layerPublic}>
        <div role="radiogroup" aria-label={t.mapLayer} className="space-y-3">
          {(staff ? GROUPS : [{ id: null, label: "", hint: undefined }]).map((g) => (
            <div key={g.id ?? "all"} className="space-y-0.5">
              {g.label && <div className="px-1 text-2xs font-semibold text-muted">{g.label}</div>}
              {g.hint && <p className="hint px-1 pb-0.5">{g.hint}</p>}
              {catalogue.filter((l) => g.id === null || l.group === g.id).map((l) => (
                <LayerRow
                  key={l.id}
                  label={l.label}
                  hint={l.hint}
                  icon={l.icon}
                  checked={layer === l.id}
                  onSelect={() => pickLayer(l.id)}
                  badge={layer === l.id && kind ? <KindBadge kind={kind} /> : undefined}
                />
              ))}
            </div>
          ))}
          <LayerRow label={t.none} icon={Building2} checked={layer === null} onSelect={() => pickLayer(null)} />
        </div>
      </Section>

      <Section title={t.where}>
        {staff ? (
          <AreaPicker area={area} onChange={setArea} drawing={drawing} onDraw={toggleDraw} />
        ) : (
          <AreaPicker area={area} onChange={setArea} label={t.partOfCity} simple />
        )}
      </Section>

      {staff && <Section title={t.when}>
        <input
          type="range"
          min={0}
          max={24}
          value={24 - hoursAgo}
          onChange={(e) => setHoursAgo(24 - Number(e.target.value))}
          className="w-full"
          aria-label={t.timeAria}
          aria-valuetext={hoursAgo === 0 ? t.now : t.hoursAgo(hoursAgo)}
        />
        <div className="flex justify-between text-2xs text-muted">
          <span>{t.ago24}</span>
          <span>{t.now}</span>
        </div>
        <p className="text-sm">
          {t.showing} <span className="font-semibold">{hoursAgo === 0 ? t.nowLatest : t.hoursAgoShown(hoursAgo)}</span>
        </p>
      </Section>}

      {staff && <Section title={t.display} collapsible>
        <div>
          <label className="check">
            <input type="checkbox" checked={showUncertainty} onChange={(e) => setShowUncertainty(e.target.checked)} />
            {t.showUncertainty}
          </label>
          <p className="hint ml-6">{t.lessCertain}</p>
        </div>
        <label className="block space-y-1">
          <span className="block text-xs font-semibold text-ink">{t.buildings}</span>
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
                {roofLabel(k)}
              </span>
            ))}
            <span className="hint col-span-2">{t.centreOnly}</span>
          </div>
        )}
        <label className="check">
          <input type="checkbox" checked={showTrees} onChange={(e) => setShowTrees(e.target.checked)} />
          {t.trees}
        </label>
      </Section>}

      <Section title={staff ? t.evidenceStaff : t.evidencePublic} collapsible defaultOpen={staff}>
        {error && (
          <Callout tone="error" title={t.loadError}>
            {error}
          </Callout>
        )}
        {env ? (
          <RunMeta env={env} />
        ) : busy ? (
          <Skeleton lines={2} />
        ) : (
          !error && <p className="hint">{t.runRecord}</p>
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
        focus={camera}
        onHover={onHover}
        onPick={onPick}
        onZoomStep={setZoom}
        onClick={drawing ? (p) => setDraft((d) => [...d, [p.lon, p.lat]]) : undefined}
      />

      <MapFloat position="top-left" className="max-w-[min(22rem,calc(100%-6rem))]">
        <div role="status" aria-live="polite" className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{layerLabel(layer, audience)}</span>
            {layer && kind && !busy && <KindBadge kind={kind} />}
          </div>
          <div className="text-xs text-muted">
            {!layer ? (
              t.noLayer
            ) : busy ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3.5 w-3.5" />
                {t.loading}
              </span>
            ) : error ? (
              <span className="text-danger">{staff ? t.errStaff : t.errPublic(error)}</span>
            ) : refusal ? (
              <span className="inline-flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-estimated" aria-hidden="true" />
                {refusal}
              </span>
            ) : empty ? (
              <span className="inline-flex items-center gap-1.5 text-estimated">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                {t.emptyArea}
              </span>
            ) : data ? (
              <span>
                <span className="num text-ink">{data.items.length.toLocaleString(locale())}</span> {things} ·{" "}
                {areaLabel(area)}
              </span>
            ) : null}
          </div>
          {!busy && !error && data?.truncated && data.count ? (
            <p className="flex gap-1.5 text-xs text-estimated">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>
                {t.incomplete(data.items.length.toLocaleString(locale()), data.count.toLocaleString(locale()), things)}
              </span>
            </p>
          ) : null}
        </div>
      </MapFloat>

      {layer && data && extent && data.items.length > 0 && (
        <MapFloat position="bottom-left" className={pointStyle(data) === "sites" && data.kind === "points" ? "" : "w-64"}>
          {data.kind === "points" && pointStyle(data) === "sites" ? (
            <div className="flex items-center gap-2 text-xs">
              <span
                className="inline-block h-3 w-3 rounded-full border border-surface"
                style={{ background: `rgb(${palette.point.join(" ")})` }}
                aria-hidden="true"
              />
              {t.onePer} {data.metric === "site" ? t.site : (metricInfo(data.metric).each ?? t.record)}
            </div>
          ) : (
            <div className="space-y-1.5">
              {metrics.length > 1 && (
                <Field label={t.valueShown}>
                  <select className="input btn-sm w-full" value={data.metric} onChange={(e) => setMetric(e.target.value)}>
                    {metrics.map((m) => (
                      <option key={m} value={m}>
                        {metricInfo(m).label}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <div className="text-xs font-semibold text-ink">{legendTitle(data)}</div>
              {formatValue(extent.min) === formatValue(extent.max) ? (
                // One value everywhere (a calm night, a dry hour): a colour scale from x to x would say nothing.
                <p className="text-xs">
                  {t.sameEverywhere}{" "}
                  <span className="num font-semibold text-ink">
                    {formatValue(extent.min)}
                    {unit}
                  </span>
                </p>
              ) : (
                <LegendRamp
                  gradient={rampGradient()}
                  low={`${formatValue(extent.min)}${unit}`}
                  high={`${formatValue(extent.max)}${unit}`}
                />
              )}
              {data.metric === "count" && <p className="hint">{t.biggerDot}</p>}
              {showUncertainty && hasUncertainty && <p className="hint">{t.faded}</p>}
              {data.calibration && (data.calibration === "calibrated" || data.calibration === "uncalibrated") && (
                <p className="hint">{calibrationLabel(data.calibration)}</p>
              )}
              {data.items.some((i) => i.synthetic) && (
                <p className="flex items-center gap-1.5 text-2xs text-muted">
                  <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-dashed border-simulated" aria-hidden="true" />
                  {t.outlined}
                </p>
              )}
            </div>
          )}
        </MapFloat>
      )}

      {hover && hovered && <ResourceHover x={hover.x} y={hover.y} resource={hovered} kind={kind} />}
      {detail && (
        <ResourceDetail
          resource={detail}
          kind={kind}
          staff={staff}
          onClose={() => setSelected(null)}
          onZoomTo={detail.position ? () => setCamera({ lon: detail.position![0], lat: detail.position![1], zoom: 16.5, pitch: 60 }) : undefined}
        />
      )}
    </Workspace>
  );
}
