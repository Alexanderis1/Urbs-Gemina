// Shared pieces of the residents' map screens (Ambiente, Trasporti, Sociale). Mobile first: the map on top,
// a sheet with the answer under it; on a desk screen the sheet becomes the left panel.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { LocateFixed, MapPin, X } from "lucide-react";
import type { DataKind } from "@/api/types";
import { KindBadge } from "@/components/Badge";
import { GlyphIcon } from "@/components/MarkerCard";
import { RunMeta } from "@/components/RunMeta";
import { Callout, Skeleton, Spinner } from "@/components/ui";
import { rampColor } from "@/lib/colors";
import { cellSpacingM, inRome, shareBelow, type CityHeatmap, type HeatCell, type HereAnswer, type HereReading, type LegendBand } from "@/lib/here";
import { texts, tr } from "@/lib/i18n";
import { formatValue } from "@/lib/layers";
import type { Loaded } from "@/lib/useCitizenData";
import { locate, setPosition, usePosition, type LocateStatus } from "@/lib/usePosition";
import { useTheme } from "@/lib/useTheme";
import { CityMap, type MapFocus } from "@/map/CityMap";
import type { Glyph } from "@/map/markerGlyphs";
import { markerLayers, type Marker } from "@/map/markers";

const T = texts({
  en: {
    useMine: "Use my position",
    locating: "Finding you…",
    orTap: "or tap the map to choose a point",
    gps: "Your position",
    chosen: "Point chosen on the map",
    change: "Remove",
    status: {
      denied: "The position was not shared. Tap the map to choose a point instead.",
      outside: "You are outside Rome: tap the map to choose a point in the city.",
      unavailable: "This device did not give a position. Tap the map to choose a point.",
    } as Record<Exclude<LocateStatus, "idle" | "locating">, string>,
    here: "Here",
    range: (lo: string, hi: string) => `likely between ${lo} and ${hi}`,
    higherThan: (n: number) => `Higher than in ${n}% of the city right now.`,
    lowerThan: (n: number) => `Lower than in ${n}% of the city right now.`,
    references: "Reference values",
    others: "Also here",
    notHere: "The twin has no estimate for this point yet.",
    noAnswer: "This could not be loaded right now.",
    loadingMap: "Loading the city map…",
    noMap: "The city map for this value is not available right now.",
    zoneAverage: "Average of this part of the city",
    howWeKnow: "How we know this",
    relative: "Colours go from the lowest to the highest value in the city right now.",
  },
  it: {
    useMine: "Usa la mia posizione",
    locating: "Ti sto cercando…",
    orTap: "oppure tocca la mappa per scegliere un punto",
    gps: "La tua posizione",
    chosen: "Punto scelto sulla mappa",
    change: "Togli",
    status: {
      denied: "La posizione non è stata condivisa. Tocca la mappa per scegliere un punto.",
      outside: "Sei fuori Roma: tocca la mappa per scegliere un punto in città.",
      unavailable: "Questo dispositivo non ha dato una posizione. Tocca la mappa per scegliere un punto.",
    } as Record<Exclude<LocateStatus, "idle" | "locating">, string>,
    here: "Qui",
    range: (lo: string, hi: string) => `probabilmente tra ${lo} e ${hi}`,
    higherThan: (n: number) => `Più alto che nel ${n}% della città in questo momento.`,
    lowerThan: (n: number) => `Più basso che nel ${n}% della città in questo momento.`,
    references: "Valori di riferimento",
    others: "Sempre qui",
    notHere: "Il gemello non ha ancora una stima per questo punto.",
    noAnswer: "Al momento non è stato possibile caricarlo.",
    loadingMap: "Carico la mappa della città…",
    noMap: "La mappa della città per questo valore non è disponibile adesso.",
    zoneAverage: "Media di questa parte della città",
    howWeKnow: "Come lo sappiamo",
    relative: "I colori vanno dal valore più basso al più alto in città in questo momento.",
  },
});

type Rgb = [number, number, number];

/** Colour of one legend band: the same pale-to-dark-red scale as every other map, in steps. */
export function bandColor(index: number, bands: LegendBand[]): Rgb {
  const ids = bands.map((b) => b.index);
  const lo = Math.min(...ids, index);
  const hi = Math.max(...ids, index);
  return rampColor(hi > lo ? (index - lo) / (hi - lo) : 0);
}

/** Black or white text, whichever reads better on a band colour. */
const inkOn = ([r, g, b]: Rgb): string => (0.299 * r + 0.587 * g + 0.114 * b > 150 ? "#17324d" : "#ffffff");

/** The round coloured chip that names a level in words ("Good", "Slow"). */
export function LevelPill({ index, label, bands }: { index: number; label: string; bands: LegendBand[] }) {
  const c = bandColor(index, bands);
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold" style={{ background: `rgb(${c.join(" ")})`, color: inkOn(c) }}>
      {label}
    </span>
  );
}

/** Mobile first: the map on top and the sheet under it; from a tablet up, the sheet is a panel at the left. */
export function MapScreen({ sheet, children }: { sheet: ReactNode; children: ReactNode }) {
  return (
    <div className="flex h-full min-h-0 flex-col-reverse md:flex-row">
      <aside className="flex max-h-[52%] min-h-0 shrink-0 flex-col border-t border-line bg-surface shadow-float md:h-full md:max-h-none md:w-[23rem] md:border-r md:border-t-0 md:shadow-none">
        {sheet}
      </aside>
      <div className="relative min-h-0 min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** A row of choices that scrolls sideways on a phone. One is always chosen. */
export function Chips<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { id: T; label: string; glyph?: Glyph }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex shrink-0 gap-1.5 overflow-x-auto border-b border-line px-3 py-2 md:flex-wrap">
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.id)}
            className={`inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-semibold transition-colors duration-150 ${
              on ? "border-primary bg-primary text-white" : "border-line-strong bg-surface text-ink hover:border-link hover:bg-primary-soft"
            }`}
          >
            {o.glyph && <GlyphIcon glyph={o.glyph} className="h-4 w-4" />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Where "here" is: a button for the phone's position, the hint to tap the map, and what went wrong if it did. */
export function PositionBar() {
  const t = tr(T);
  const { position, status } = usePosition();
  if (position) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <MapPin className="h-4 w-4 shrink-0 text-link" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate font-semibold text-ink">{position.source === "gps" ? t.gps : t.chosen}</span>
        <button type="button" className="btn-quiet btn-sm" onClick={() => locate()} title={t.useMine} aria-label={t.useMine}>
          <LocateFixed className="h-4 w-4" aria-hidden="true" />
        </button>
        <button type="button" className="btn-quiet btn-sm" onClick={() => setPosition(null)}>
          <X className="h-3.5 w-3.5" aria-hidden="true" />
          {t.change}
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <button type="button" className="btn min-h-11 w-full text-base" onClick={() => locate()} disabled={status === "locating"}>
        {status === "locating" ? <Spinner /> : <LocateFixed className="h-5 w-5" aria-hidden="true" />}
        {status === "locating" ? t.locating : t.useMine}
      </button>
      <p className="text-center text-xs text-muted">{t.orTap}</p>
      {status !== "idle" && status !== "locating" && <Callout tone="warn">{t.status[status]}</Callout>}
    </div>
  );
}

/** The answer for the chosen position: one big value with its level in words, then the rest. */
export function HereCard({
  here,
  focusId,
  onFocus,
  cityValues,
  bands,
}: {
  here: Loaded<HereAnswer>;
  /** The reading shown large (the value the map is coloured by). */
  focusId: string;
  onFocus?: (id: string) => void;
  /** The city's values for the same thing now, to say how this point compares. */
  cityValues: number[];
  bands: LegendBand[];
}) {
  const t = tr(T);
  if (here.status === "idle") return null;
  if (here.status === "loading") return <Skeleton lines={3} />;
  if (here.status === "missing") return <Callout tone="warn">{t.notHere}</Callout>;
  if (here.status === "error") return <Callout tone="error" title={t.noAnswer}>{here.text}</Callout>;
  const { readings, summary } = here.data;
  const main = readings.find((r) => r.id === focusId) ?? readings[0];
  if (!main) return <Callout tone="warn">{t.notHere}</Callout>;
  const others = readings.filter((r) => r !== main);
  const share = shareBelow(cityValues, main.value);
  const kind: DataKind | undefined = main.kind ?? here.kind;
  return (
    <div className="space-y-3">
      <div className="rounded border border-line bg-sunken px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-muted">
            {main.label} · {t.here}
          </span>
          {kind && <KindBadge kind={kind} />}
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="num text-4xl font-bold leading-none text-ink">{formatValue(main.value)}</span>
          <span className="text-sm text-muted">{main.unit}</span>
          {main.level && <LevelPill index={main.level.index} label={main.level.label} bands={bands} />}
        </div>
        {main.low !== undefined && main.high !== undefined && (
          <p className="mt-1 text-xs text-muted">{t.range(formatValue(main.low), `${formatValue(main.high)} ${main.unit}`)}</p>
        )}
      </div>
      {summary && <p className="text-sm leading-relaxed text-ink">{summary}</p>}
      {share !== null && cityValues.length > 20 && (
        <p className="text-sm text-muted">{share >= 50 ? t.higherThan(share) : t.lowerThan(100 - share)}</p>
      )}
      {others.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="label">{t.others}</h3>
          <div className="grid grid-cols-3 gap-1.5">
            {others.map((r) => (
              <OtherReading key={r.id} r={r} bands={bands} onClick={onFocus ? () => onFocus(r.id) : undefined} />
            ))}
          </div>
        </section>
      )}
      {main.references.length > 0 && (
        <details className="rounded border border-line">
          <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-link">{t.references}</summary>
          <ul className="space-y-1.5 px-3 pb-3 text-sm">
            {main.references.map((ref) => (
              <li key={ref.name} className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 text-muted">
                  {ref.name}
                  {ref.averaging ? ` (${ref.averaging})` : ""}
                  {ref.source && <span className="block text-2xs">{ref.source}</span>}
                </span>
                {ref.value !== undefined && (
                  <span className="num shrink-0 font-semibold text-ink">
                    {formatValue(ref.value)} {main.unit}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      <details className="rounded border border-line">
        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-link">{t.howWeKnow}</summary>
        <div className="px-3 pb-3">
          <RunMeta env={here.env} />
        </div>
      </details>
    </div>
  );
}

function OtherReading({ r, bands, onClick }: { r: HereReading; bands: LegendBand[]; onClick?: () => void }) {
  const body = (
    <>
      <span className="block text-2xs font-semibold text-muted">{r.label}</span>
      <span className="num block text-base font-bold leading-tight text-ink">{formatValue(r.value)}</span>
      {r.level ? <LevelPill index={r.level.index} label={r.level.label} bands={bands} /> : <span className="text-2xs text-muted">{r.unit}</span>}
    </>
  );
  const cls = "rounded border border-line px-2 py-1.5 text-left";
  return onClick ? (
    <button type="button" className={`${cls} transition-colors duration-150 hover:border-link hover:bg-primary-soft`} onClick={onClick}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  );
}

/** What the colours of the heatmap mean: the tool's own bands in words, or a low-to-high scale. */
export function HeatLegend({ heat, unit, invert = false }: { heat: CityHeatmap; unit: string; invert?: boolean }) {
  const t = tr(T);
  if (heat.legend.length) {
    return (
      <div className="flex flex-wrap gap-1">
        {heat.legend.map((b) => (
          <LevelPill key={b.index} index={b.index} label={b.label} bands={heat.legend} />
        ))}
      </div>
    );
  }
  const values = heat.cells.map((c) => c.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const stops = [0, 0.25, 0.5, 0.75, 1].map((s) => `rgb(${rampColor(invert ? 1 - s : s).join(" ")})`);
  return (
    <div>
      <div className="h-2 rounded-sm border border-line" style={{ background: `linear-gradient(90deg, ${stops.join(", ")})` }} />
      <div className="num mt-1 flex justify-between text-2xs text-muted">
        <span>
          {formatValue(lo)} {unit}
        </span>
        <span>
          {formatValue(hi)} {unit}
        </span>
      </div>
      <p className="hint mt-1">{t.relative}</p>
    </div>
  );
}

/** Whole-city view: wide enough to see all of Rome on a phone. */
const CITY_ZOOM = 10.2;
/** Close enough to see the 3D buildings around the point, wide enough to see the neighbouring patches of the heatmap. */
const HERE_ZOOM = 12.7;

/**
 * The map of a citizen screen: the city heatmap, the chosen position as a 3D marker, any extra markers of the
 * screen, and a small card under the pointer. A click or tap on the map chooses the position.
 */
export function CitizenMap<T>({
  heat,
  heatLabel,
  unit,
  invert = false,
  markers = [],
  selectedId,
  onPickMarker,
  describeMarker,
  focus,
  children,
}: {
  heat: Loaded<CityHeatmap>;
  heatLabel: string;
  unit: string;
  /** True when a low value is the bad one (road speed). Only used without the tool's own bands. */
  invert?: boolean;
  markers?: Marker<T>[];
  selectedId?: string | null;
  onPickMarker?: (m: Marker<T> | null) => void;
  /** Title and one line for the card under the pointer. */
  describeMarker?: (m: Marker<T>) => { title: string; line?: string };
  /** Camera target set by the screen (e.g. a place chosen in the list). */
  focus?: MapFocus | null;
  children?: ReactNode;
}) {
  const t = tr(T);
  const { palette } = useTheme();
  const { position } = usePosition();
  const [zoom, setZoom] = useState(CITY_ZOOM);
  const [hover, setHover] = useState<{ x: number; y: number; title: string; line?: string; level?: number } | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [camera, setCamera] = useState<MapFocus | null>(null);

  useEffect(() => {
    if (position) setCamera({ lon: position.lon, lat: position.lat, zoom: HERE_ZOOM, pitch: 50 });
  }, [position]);
  useEffect(() => {
    if (focus) setCamera(focus);
  }, [focus]);

  const cells = heat.status === "ok" ? heat.data.cells : null;
  const bands = heat.status === "ok" ? heat.data.legend : [];
  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (cells?.length) {
      const spacing = cellSpacingM(cells) ?? 1500;
      const values = cells.map((c) => c.value);
      const lo = Math.min(...values);
      const hi = Math.max(...values);
      const norm = (v: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
      const colour = (c: HeatCell): Rgb => (c.level !== undefined && bands.length ? bandColor(c.level, bands) : rampColor(invert ? 1 - norm(c.value) : norm(c.value)));
      const tiles = cells.every((c) => c.h3);
      out.push(
        tiles
          ? // The twin's own hexagons: clean tiles that cover the city without gaps or overlaps.
            new H3HexagonLayer<HeatCell>({
              id: "heat",
              data: cells,
              getHexagon: (c) => c.h3!,
              extruded: false,
              getFillColor: (c) => [...colour(c), 135],
              stroked: true,
              getLineColor: [255, 255, 255, 70],
              lineWidthUnits: "pixels",
              getLineWidth: 1,
              pickable: true,
              updateTriggers: { getFillColor: [lo, hi, bands, invert] },
            })
          : // Any other grid: round patches that just touch.
            new ScatterplotLayer<HeatCell>({
              id: "heat",
              data: cells,
              getPosition: (c) => [c.lon, c.lat],
              getRadius: spacing * 0.5,
              radiusUnits: "meters",
              getFillColor: (c) => [...colour(c), 135],
              stroked: false,
              pickable: true,
              updateTriggers: { getFillColor: [lo, hi, bands, invert] },
            }),
      );
    }
    out.push(...markerLayers(markers, { id: "mk", zoom, palette, selectedId, hoveredId: hoverId }));
    if (position) {
      const me: Marker<null> = { id: "me", position: [position.lon, position.lat], color: palette.accent, level: null, glyph: "here", data: null };
      out.push(...markerLayers([me], { id: "me", zoom, palette, selectedId: "me" }));
    }
    return out;
  }, [cells, bands, invert, markers, zoom, palette, selectedId, hoverId, position]);

  const onHover = (info: PickingInfo) => {
    const id = info.layer?.id ?? "";
    if (info.object && id.startsWith("mk-")) {
      const m = info.object as Marker<T>;
      setHoverId(m.id);
      setHover({ x: info.x, y: info.y, ...(describeMarker?.(m) ?? { title: m.text ?? "" }) });
    } else if (info.object && id === "heat") {
      const c = info.object as HeatCell;
      setHoverId(null);
      setHover({
        x: info.x,
        y: info.y,
        title: `${heatLabel}: ${formatValue(c.value)} ${unit}`,
        line: t.zoneAverage,
        level: c.level,
      });
    } else {
      setHoverId(null);
      setHover(null);
    }
  };

  // A marker takes the click (its card opens); anywhere else on the map chooses the position.
  const onPick = (info: PickingInfo): boolean => {
    const id = info.layer?.id ?? "";
    if (info.object && id.startsWith("mk-")) {
      onPickMarker?.(info.object as Marker<T>);
      return true;
    }
    onPickMarker?.(null);
    return false;
  };

  const band = hover?.level !== undefined ? bands.find((b) => b.index === hover.level) : undefined;
  return (
    <>
      <CityMap
        layers={layers}
        initialZoom={CITY_ZOOM}
        pitch={35}
        focus={camera}
        onHover={onHover}
        onPick={onPick}
        onZoomStep={setZoom}
        onClick={(p) => {
          if (inRome(p.lon, p.lat)) setPosition({ lon: Math.round(p.lon * 1e5) / 1e5, lat: Math.round(p.lat * 1e5) / 1e5, source: "map" });
        }}
      />
      {heat.status === "loading" && (
        <div role="status" className="map-float absolute left-3 top-3 z-10 flex items-center gap-2 px-3 py-2 text-xs text-muted">
          <Spinner className="h-3.5 w-3.5" />
          {t.loadingMap}
        </div>
      )}
      {(heat.status === "missing" || heat.status === "error") && (
        <div role="status" className="map-float absolute left-3 top-3 z-10 max-w-[80%] px-3 py-2 text-xs text-estimated">
          {t.noMap}
        </div>
      )}
      {hover && hover.title && (
        <div className="map-float pointer-events-none absolute z-20 max-w-[16rem] animate-fade-in px-2.5 py-1.5 text-xs" style={{ left: hover.x + 14, top: hover.y + 14 }} role="tooltip">
          <div className="font-semibold text-ink">{hover.title}</div>
          {hover.line && <div className="text-muted">{hover.line}</div>}
          {band && (
            <div className="mt-1">
              <LevelPill index={band.index} label={band.label} bands={bands} />
            </div>
          )}
        </div>
      )}
      {children}
    </>
  );
}
