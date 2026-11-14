// The citizen services: "what is it like here, now" on top of the whole city.
// Pure helpers and readers for the citizen tools (air_here, emf_here, city_heatmap, transport_now, places_open).
// The tools give every judgement (levels, reference values); this file never holds a threshold.
import { cellToLatLng, cellToParent, latLngToCell } from "h3-js";
import type { DataKind } from "@/api/types";
import { getLang, texts, tr } from "@/lib/i18n";
import { prettyUnit, type MapItem } from "@/lib/layers";

/** Box around Roma Capitale (config/areas, the same the tools use for "city"). */
const ROME_BOX = [12.234, 41.655, 12.856, 42.141] as const;

export function inRome(lon: number, lat: number): boolean {
  return lon >= ROME_BOX[0] && lon <= ROME_BOX[2] && lat >= ROME_BOX[1] && lat <= ROME_BOX[3];
}

const M_PER_DEG = 111_320;

/** A square of `halfSideM` metres each way around a position, as the GeoJSON polygon the layer tools take. */
export function aroundPolygon(lon: number, lat: number, halfSideM: number): { type: "Polygon"; coordinates: number[][][] } {
  const dLat = halfSideM / M_PER_DEG;
  const dLon = halfSideM / (M_PER_DEG * Math.cos((lat * Math.PI) / 180));
  const r = (n: number) => Math.round(n * 1e6) / 1e6;
  const ring = [
    [r(lon - dLon), r(lat - dLat)],
    [r(lon + dLon), r(lat - dLat)],
    [r(lon + dLon), r(lat + dLat)],
    [r(lon - dLon), r(lat + dLat)],
    [r(lon - dLon), r(lat - dLat)],
  ];
  return { type: "Polygon", coordinates: [ring] };
}

function distance2(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const x = (lon1 - lon2) * Math.cos((lat1 * Math.PI) / 180);
  const y = lat1 - lat2;
  return x * x + y * y;
}

/** The estimate for the cell the position falls in (or the closest one returned). */
export function nearestCell<T extends Pick<MapItem, "h3">>(items: T[], lon: number, lat: number): T | null {
  let best: T | null = null;
  let bestD = Infinity;
  for (const i of items) {
    if (!i.h3) continue;
    const [clat, clon] = cellToLatLng(i.h3);
    const d = distance2(lon, lat, clon, clat);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/** Share (0-100) of the city's values that are lower than `value`. Null without values. */
export function shareBelow(values: number[], value: number): number | null {
  if (!values.length) return null;
  return Math.round((values.filter((v) => v < value).length / values.length) * 100);
}

/** One patch of the city heatmap. */
export interface HeatCell {
  lon: number;
  lat: number;
  value: number;
  low?: number;
  high?: number;
  /** Band of the tool's legend, when the tool judges the value. */
  level?: number;
  /** The hexagon this patch is, when it was built here from the twin's own grid. */
  h3?: string;
}

/**
 * Fallback when the heatmap tool is not there: the fine cells of a (thinned) city answer are merged into
 * larger hexagons by averaging, so the whole city is covered. `low`/`high` keep the widest range seen.
 */
export function coarseCells(items: Pick<MapItem, "h3" | "value" | "p5" | "p95">[], resolution: number): HeatCell[] {
  const groups = new Map<string, { sum: number; n: number; low?: number; high?: number }>();
  for (const i of items) {
    if (!i.h3) continue;
    const parent = cellToParent(i.h3, resolution);
    const g = groups.get(parent) ?? { sum: 0, n: 0 };
    g.sum += i.value;
    g.n += 1;
    if (i.p5 !== undefined) g.low = g.low === undefined ? i.p5 : Math.min(g.low, i.p5);
    if (i.p95 !== undefined) g.high = g.high === undefined ? i.p95 : Math.max(g.high, i.p95);
    groups.set(parent, g);
  }
  return [...groups].map(([h3, g]) => {
    const [lat, lon] = cellToLatLng(h3);
    return { lon, lat, h3, value: g.sum / g.n, ...(g.low !== undefined ? { low: g.low } : {}), ...(g.high !== undefined ? { high: g.high } : {}) };
  });
}

/** Typical distance in metres between neighbouring cells (from a sample), to size the patches. Null for fewer than two. */
export function cellSpacingM(cells: Pick<HeatCell, "lon" | "lat">[]): number | null {
  if (cells.length < 2) return null;
  const sample = cells.slice(0, 60);
  const nearest: number[] = [];
  for (const a of sample) {
    let best = Infinity;
    for (const b of cells) {
      if (a === b) continue;
      const d = distance2(a.lon, a.lat, b.lon, b.lat);
      if (d > 0 && d < best) best = d;
    }
    if (best < Infinity) nearest.push(Math.sqrt(best) * M_PER_DEG);
  }
  if (!nearest.length) return null;
  nearest.sort((x, y) => x - y);
  return nearest[Math.floor(nearest.length / 2)]!;
}

/** The fine cell (resolution 9, the twin's grid) a position falls in. */
export function cellAt(lon: number, lat: number): string {
  return latLngToCell(lat, lon, 9);
}

// ---- Readers for the citizen tools. Tolerant: a missing field is left out, never invented. ----

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string | undefined => (typeof v === "string" && v.trim() ? v.trim() : undefined);
const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter(isObj) : []);

/** Picks the text in the current language: `<key>_it` / `<key>_en`, then the bare key. */
function localized(o: Record<string, unknown>, key: string): string | undefined {
  const lang = getLang();
  return str(o[`${key}_${lang}`]) ?? str(o[key]) ?? str(o[`${key}_it`]) ?? str(o[`${key}_en`]);
}

const KINDS: readonly string[] = ["real", "estimated", "simulated", "not_available", "hypothetical"];
const kindOf = (v: unknown): DataKind | undefined => (typeof v === "string" && KINDS.includes(v) ? (v as DataKind) : undefined);

export interface Level {
  index: number;
  label: string;
}

export interface Reference {
  name: string;
  value?: number;
  averaging?: string;
  source?: string;
}

const REF = texts({
  en: {
    hourly_limit: "Hourly limit",
    daily_limit: "Daily limit",
    annual_limit: "Yearly limit",
    information_1h: "Information threshold (1 hour)",
    alert_1h: "Alert threshold (1 hour)",
    target_8h: "Target value (8 hours)",
    attention_value: "Attention value",
    exposure_limit: "Exposure limit",
  } as Record<string, string>,
  it: {
    hourly_limit: "Limite orario",
    daily_limit: "Limite giornaliero",
    annual_limit: "Limite annuale",
    information_1h: "Soglia di informazione (1 ora)",
    alert_1h: "Soglia di allarme (1 ora)",
    target_8h: "Valore obiettivo (8 ore)",
    attention_value: "Valore di attenzione",
    exposure_limit: "Limite di esposizione",
  } as Record<string, string>,
});

/** The tools name a reference value by its key ("no2_hourly_limit"); people read "Hourly limit". Only the name: the value comes from the tool. */
export function referenceLabel(name: string): string {
  const t = tr(REF);
  const key = Object.keys(t).find((k) => name === k || name.endsWith(`_${k}`));
  return key ? t[key]! : name;
}

export interface HereReading {
  id: string;
  label: string;
  value: number;
  low?: number;
  high?: number;
  unit: string;
  kind?: DataKind;
  level?: Level;
  references: Reference[];
}

export interface HereAnswer {
  summary?: string;
  readings: HereReading[];
}

function level(v: unknown): Level | undefined {
  if (!isObj(v)) return undefined;
  const index = num(v.index);
  const label = localized(v, "label");
  return index !== undefined && label ? { index, label } : undefined;
}

function references(v: unknown): Reference[] {
  return list(v)
    .map((r) => ({ name: referenceLabel(localized(r, "name") ?? ""), value: num(r.value), averaging: localized(r, "averaging"), source: str(r.source) }))
    .filter((r) => r.name);
}

function hereReading(o: Record<string, unknown>, fallbackId: string): HereReading | null {
  const value = num(o.value);
  if (value === undefined) return null;
  const id = str(o.id) ?? fallbackId;
  return {
    id,
    label: localized(o, "label") ?? id,
    value,
    low: num(o.low),
    high: num(o.high),
    unit: prettyUnit(str(o.unit) ?? ""),
    kind: kindOf(o.kind),
    level: level(o.level),
    references: references(o.references),
  };
}

export function parseAirHere(result: unknown): HereAnswer {
  const r = isObj(result) ? result : {};
  return {
    summary: localized(r, "summary"),
    readings: list(r.pollutants)
      .map((p) => hereReading(p, "value"))
      .filter((p): p is HereReading => p !== null),
  };
}

export function parseEmfHere(result: unknown): HereAnswer {
  const r = isObj(result) ? result : {};
  const one = hereReading({ id: "emf", ...r }, "emf");
  return { summary: localized(r, "summary"), readings: one ? [one] : [] };
}

export interface LegendBand {
  index: number;
  label: string;
  from?: number;
  to?: number;
}

export interface CityHeatmap {
  cells: HeatCell[];
  legend: LegendBand[];
  unit: string;
}

/** Layers whose bands the tool lists from worst to best. Basis: citizen.congestion in config/tools.yaml ("band 1 = slowest"). */
const WORST_FIRST: ReadonlySet<string> = new Set(["road_speed"]);

export function parseCityHeatmap(result: unknown): CityHeatmap {
  const r = isObj(result) ? result : {};
  const cells: HeatCell[] = [];
  for (const c of list(r.cells)) {
    const lon = num(c.lon);
    const lat = num(c.lat);
    const value = num(c.value);
    if (lon === undefined || lat === undefined || value === undefined) continue;
    const lvl = isObj(c.level) ? num(c.level.index) : num(c.level);
    const h3 = str(c.cell) ?? str(c.h3);
    cells.push({
      ...(h3 ? { h3 } : {}),
      lon,
      lat,
      value,
      ...(num(c.low) !== undefined ? { low: num(c.low) } : {}),
      ...(num(c.high) !== undefined ? { high: num(c.high) } : {}),
      ...(lvl !== undefined ? { level: lvl } : {}),
    });
  }
  const legend: LegendBand[] = [];
  for (const b of list(r.legend)) {
    const index = num(b.index);
    const label = localized(b, "label");
    if (index === undefined || !label) continue;
    legend.push({ index, label, ...(num(b.from) !== undefined ? { from: num(b.from) } : {}), ...(num(b.to) !== undefined ? { to: num(b.to) } : {}) });
  }
  const ratioBands = WORST_FIRST.has(str(r.layer) ?? "");
  // The bands of a ratio scale are not in the unit of the values, so their unit is not borrowed.
  const unit = str(r.unit) ?? (ratioBands ? undefined : list(r.legend).map((b) => str(b.unit)).find(Boolean)) ?? "";
  if (ratioBands && legend.length) {
    // Turned round so that, as on every other scale of the app, a higher band is a worse one.
    const flip = (i: number) => legend.length + 1 - i;
    legend.reverse().forEach((b) => (b.index = flip(b.index)));
    cells.forEach((c) => c.level !== undefined && (c.level = flip(c.level)));
  }
  return { cells, legend, unit: prettyUnit(unit) };
}

export interface TransportEvent {
  id?: string;
  title: string;
  category: string;
  /** The category in words, as the tool writes it (Italian). */
  categoryLabel?: string;
  /** Street the notice is about, when it names one. */
  street?: string;
  start?: string;
  end?: string;
  source?: string;
  description?: string;
  lines: string[];
  position?: [number, number];
}

export interface FeedState {
  id: string;
  lastUpdate?: string;
  stale: boolean;
}

export function parseTransportNow(result: unknown): { events: TransportEvent[]; feeds: FeedState[] } {
  const r = isObj(result) ? result : {};
  const events: TransportEvent[] = [];
  for (const e of list(r.events)) {
    const title = localized(e, "title");
    if (!title) continue;
    const lon = num(e.lon);
    const lat = num(e.lat);
    events.push({
      id: str(e.id),
      title,
      category: str(e.category) ?? "avviso",
      categoryLabel: str(e.category_label),
      street: str(e.street),
      start: str(e.start),
      end: str(e.end),
      source: str(e.source),
      description: localized(e, "description"),
      lines: Array.isArray(e.lines) ? e.lines.map((l) => String(l)).filter(Boolean) : [],
      ...(lon !== undefined && lat !== undefined ? { position: [lon, lat] as [number, number] } : {}),
    });
  }
  const feeds = list(r.feeds)
    .map((f) => ({ id: str(f.id) ?? "", lastUpdate: str(f.last_update), stale: f.stale === true }))
    .filter((f) => f.id);
  return { events, feeds };
}

export interface OpenPlace {
  name: string;
  address?: string;
  category?: string;
  hours?: string;
  /** True = open at the chosen time, false = closed, null = opening hours unknown. */
  open: boolean | null;
  /** Who says the hours ("declared by the manager"). */
  hoursNote?: string;
  /** Metres from the chosen position. */
  distanceM?: number;
  /** Ticket: "yes", "no" or a short note, as the source writes it. */
  fee?: string;
  /** Step-free access: "yes", "limited" or "no", as the source writes it. */
  wheelchair?: string;
  website?: string;
  disciplines?: string[];
  source?: string;
  position: [number, number];
}

export function parsePlacesOpen(result: unknown): { places: OpenPlace[]; coverage?: { withHours: number; total: number } } {
  const r = isObj(result) ? result : {};
  const places: OpenPlace[] = [];
  for (const p of list(r.places)) {
    const lon = num(p.lon);
    const lat = num(p.lat);
    const name = str(p.name);
    if (lon === undefined || lat === undefined || !name) continue;
    places.push({
      name,
      address: str(p.address),
      category: str(p.category),
      hours: str(p.opening_hours),
      open: typeof p.open_at === "boolean" ? p.open_at : null,
      hoursNote: str(p.hours_note),
      distanceM: num(p.distance_m),
      fee: str(p.fee),
      wheelchair: str(p.wheelchair),
      website: str(p.website),
      ...(Array.isArray(p.disciplines) && p.disciplines.length ? { disciplines: p.disciplines.map((d) => String(d)) } : {}),
      source: str(p.source),
      position: [lon, lat],
    });
  }
  const c = isObj(r.coverage) ? r.coverage : null;
  const withHours = c ? num(c.with_hours) : undefined;
  const total = c ? num(c.total) : undefined;
  return { places, ...(withHours !== undefined && total !== undefined ? { coverage: { withHours, total } } : {}) };
}

/**
 * Italian sport names and how the facility registers (OpenStreetMap tags, Roma Capitale) write them.
 * Basis: OSM `sport=*` values and the discipline names in the Roma Capitale facility register.
 */
const SPORT_WORDS: Record<string, string[]> = {
  calcio: ["calcio", "soccer", "football"],
  calcetto: ["calcetto", "calcio a 5", "futsal", "five-a-side", "soccer"],
  nuoto: ["nuoto", "swimming", "piscina"],
  tennis: ["tennis"],
  padel: ["padel", "paddle"],
  basket: ["basket", "basketball", "pallacanestro"],
  pallavolo: ["pallavolo", "volleyball", "volley"],
  atletica: ["atletica", "athletics", "running"],
  palestra: ["palestra", "fitness", "gym", "ginnastica", "gymnastics"],
};

/**
 * Fallback for "where can I do this sport" when the opening-hours tool is not there: the facility register,
 * filtered by sport and (with a point) by distance. Without hours a place is never called open.
 */
export function placesFromFacilities(
  features: unknown[],
  query: { sport?: string; point?: { lon: number; lat: number } | null; radiusM?: number },
): OpenPlace[] {
  const words = query.sport ? (SPORT_WORDS[query.sport.toLowerCase()] ?? [query.sport.toLowerCase()]) : null;
  const out: (OpenPlace & { d: number })[] = [];
  for (const f of features.filter(isObj)) {
    const g = isObj(f.geometry) ? f.geometry : null;
    const p = isObj(f.properties) ? f.properties : {};
    if (!g || !Array.isArray(g.coordinates)) continue;
    const lon = num(g.coordinates[0]);
    const lat = num(g.coordinates[1]);
    if (lon === undefined || lat === undefined) continue;
    const disciplines = Array.isArray(p.disciplines) ? p.disciplines.map((d) => String(d).toLowerCase()) : [];
    if (words && !disciplines.some((d) => words.some((w) => d.includes(w)))) continue;
    const d = query.point ? Math.sqrt(distance2(lon, lat, query.point.lon, query.point.lat)) * M_PER_DEG : 0;
    if (query.point && d > (query.radiusM ?? 3000)) continue;
    const first = disciplines[0];
    out.push({
      name: str(p.name) ?? (first ? first[0]!.toUpperCase() + first.slice(1) : (str(p.kind) ?? "Sport")),
      category: disciplines.slice(0, 3).join(", ") || str(p.kind),
      open: p.closed === true ? false : null,
      position: [lon, lat],
      d,
    });
  }
  if (query.point) out.sort((a, b) => a.d - b.d);
  return out.map(({ d: _d, ...place }) => place);
}
