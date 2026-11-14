// Reads any run_scenario result generically: the eight kinds return different fields, so the screen is driven by
// what is present. Numbers are passed through (rounded for display only); nothing is computed here.

import { inRome } from "@/lib/mapActions";
import { locale, texts, tr } from "@/lib/i18n";

export interface Quantile {
  p5: number;
  p50: number;
  p95: number;
}

export interface QuantileItem {
  path: string;
  label: string;
  unit: string;
  value: Quantile;
}

export interface FactItem {
  path: string;
  label: string;
  value: string;
  /** For a single number: the figure without its unit, and the unit, so a tile can set them apart. */
  bare?: string;
  unit?: string;
  /** Caveat to show under the figure, e.g. when only the middle estimate was returned. */
  note?: string;
}

/** A headline figure for the result panel: a range (with its note) or a single returned number. */
export interface KeyFigure {
  path: string;
  label: string;
  value: string;
  unit: string;
  note?: string;
}

export interface TableItem {
  path: string;
  label: string;
  columns: string[];
  /** First rows only (see MAX_ROWS); `total` is the full count. */
  rows: string[][];
  total: number;
}

export interface FootprintItem {
  path: string;
  label: string;
  /** likely = P50 or "likely" zone; possible = P95 or "possible" zone. */
  level: "likely" | "possible";
  geometry: { type: string; coordinates?: unknown };
}

export interface PlaceItem {
  lon: number;
  lat: number;
  label: string;
  table: string;
}

/** One measure of a run that reports today, the change and their difference side by side (traffic). */
export interface ComparisonRow {
  path: string;
  label: string;
  unit: string;
  baseline: Quantile;
  variant: Quantile;
  difference: Quantile | null;
}

export interface ScenarioSummary {
  /** Today vs the change: the top-level pair, or the first nested {baseline, variant} pair (then `label` names it). */
  compare: { baseline: Quantile; variant: Quantile; label?: string; path?: string } | null;
  /** Filled when baseline and variant each hold several measures; `compare` is then the first row. */
  comparisons: ComparisonRow[];
  quantiles: QuantileItem[];
  facts: FactItem[];
  tables: TableItem[];
  footprints: FootprintItem[];
  points: PlaceItem[];
  notAvailable: string | null;
}

export const MAX_ROWS = 8;
const MAX_POINTS = 500;

/** Shown elsewhere on screen (title, compare bars) or bookkeeping. */
const TOP_SKIP = new Set(["kind", "metric", "unit", "status", "reason"]);
/** Path segments that add nothing to a label. */
const LABEL_SKIP = new Set(["zones", "sites", "rows", "items"]);

/** Row order for runs with several measures: what a driver feels first, bookkeeping last. */
const COMPARISON_ORDER = ["mean_travel_time_s", "mean_time_loss_s", "vehicle_hours_lost"];

const T = texts({
  en: {
    dict: {
      mean_travel_time_s: "Average trip time",
      mean_time_loss_s: "Average delay per trip",
      vehicle_hours_lost: "Hours lost by all vehicles",
      completed: "Trips completed",
      area: "Operating area",
      km2: "Area",
      baseline: "Today",
      p50: "Middle estimate (P50)",
      id: "Id",
      children_0_14: "Children (0-14)",
      median_resident: "Median resident",
      p75_resident: "75th percentile resident",
      travel_min_baseline: "Travel time today (minutes)",
      rise_m: "River rise",
      sigma_m: "Uncertainty of the rise",
      gauge: "Gauge",
      gauge_level_m: "Gauge level",
      discharge_m3s: "River discharge",
      flooded_km2: "Flooded area",
      flooded_km2_p50: "Flooded area (P50)",
      baseline_flooded_km2: "River channel today",
      alert_probability: "Chance of each alert level",
      official_hazard: "Official hazard areas",
      hot_area_km2: "Hot area",
      forecast_tmax_c: "Forecast day maximum",
      forecast_tmin_c: "Forecast night minimum",
      hot_day: "Hot day",
      tropical_night: "Tropical night",
      what_if: "What-if",
      "what_if.cooling_day_c": "Cooling by day with the change",
      cooling_day_c: "Cooling by day",
      hot_day_residents: "Residents on a hot day",
      residents_no_longer_hot: "Residents no longer hot",
      residents: "Residents",
      children: "Children",
      elderly_65_plus: "Aged 65 and over",
      residents_total: "Residents in the area",
      residents_cut_off: "Residents cut off",
      residents_beyond_target: "Residents beyond the target time",
      sections_touched: "Census sections touched",
      sections_losing_coverage: "Sections losing coverage",
      closed_roads: "Roads closed",
      facilities: "Stations",
      target_min: "Target time",
      target_source: "Target source",
      service: "Service",
      minutes_before: "Minutes before",
      minutes_after: "Minutes after",
      before: "Before",
      after: "After",
      hotspots: "Flooding hotspots",
      hotspots_count: "Hotspots found",
      hollows_modelled: "Hollows modelled",
      sections: "Census sections",
      sez_id: "Section",
      sensitive_sites: "Sensitive sites",
      official_damage_zones: "Official damage zones",
      sewer: "Sewer",
      surcharge_points: "Overflow points",
      surcharge_m3: "Overflow volume",
      surcharge_map_p50: "Sewer overflow area (P50)",
      outfalls_blocked: "Outfalls blocked by the river",
      outfalls_considered: "Outfalls considered",
      efficiency: "Drain efficiency",
      street_drain_rate_mm_h: "Street drain rate",
      mean_m3: "Mean overflow",
      max_depth_m: "Max depth",
      flooded_m2: "Flooded area",
      rain_mm_mean: "Mean rain",
      probability_over_30cm: "Chance of over 30 cm",
      duration_h: "Duration",
      total_depth_index: "Total depth index",
      members: "Ensemble members",
      model: "Model",
      calibration: "Calibration",
      probability: "Chance",
      site: "Release site",
      substance: "Substance",
      release_kg_s: "Release rate",
      wind: "Wind",
      speed_ms: "Speed",
      from_deg: "From",
      threshold_mg_m3: "Threshold",
      meaning: "Meaning",
      area_km2: "Area",
      max_distance_m: "Furthest distance over the threshold",
      footprint_p50: "Likely extent (P50)",
      footprint_p95: "Possible extent (P95)",
      hot_map_p50: "Hot area (P50)",
      footprint_possible: "Possible zone",
      impervious_pct: "Sealed ground",
      tree_cover_pct: "Tree cover",
      tmax_c: "Day maximum",
      tmin_c: "Night minimum",
      by_category: "By category",
      count: "Count",
      name: "Name",
      category: "Category",
      subtype: "Type",
      day: "Day",
    } as Record<string, string>,
    affected: {
      "residents.residents": "Residents in the affected area",
      "residents.children_0_14": "Children (0-14) in the affected area",
    } as Record<string, string>,
    notAvailable: "Not available.",
    sameEveryRun: "same in every model run",
    range: (lo: string, hi: string) => `range ${lo} to ${hi}`,
    yes: "Yes",
    no: "No",
    middleEstimate: "middle estimate (P50)",
  },
  it: {
    dict: {
      mean_travel_time_s: "Tempo medio di viaggio",
      mean_time_loss_s: "Ritardo medio per viaggio",
      vehicle_hours_lost: "Ore perse da tutti i veicoli",
      completed: "Viaggi completati",
      area: "Area operativa",
      km2: "Area",
      baseline: "Oggi",
      p50: "Stima centrale (P50)",
      id: "Id",
      children_0_14: "Bambini (0-14)",
      median_resident: "Residente mediano",
      p75_resident: "Residente al 75º percentile",
      travel_min_baseline: "Tempo di viaggio oggi (minuti)",
      rise_m: "Aumento del fiume",
      sigma_m: "Incertezza dell'aumento",
      gauge: "Idrometro",
      gauge_level_m: "Livello all'idrometro",
      discharge_m3s: "Portata del fiume",
      flooded_km2: "Area allagata",
      flooded_km2_p50: "Area allagata (P50)",
      baseline_flooded_km2: "Alveo del fiume oggi",
      alert_probability: "Probabilità di ogni livello di allerta",
      official_hazard: "Aree di pericolo ufficiali",
      hot_area_km2: "Area calda",
      forecast_tmax_c: "Massima di giorno prevista",
      forecast_tmin_c: "Minima di notte prevista",
      hot_day: "Giorno caldo",
      tropical_night: "Notte tropicale",
      what_if: "Ipotesi",
      "what_if.cooling_day_c": "Raffrescamento di giorno con la modifica",
      cooling_day_c: "Raffrescamento di giorno",
      hot_day_residents: "Residenti in un giorno caldo",
      residents_no_longer_hot: "Residenti non più al caldo",
      residents: "Residenti",
      children: "Bambini",
      elderly_65_plus: "Over 65",
      residents_total: "Residenti nell'area",
      residents_cut_off: "Residenti isolati",
      residents_beyond_target: "Residenti oltre il tempo obiettivo",
      sections_touched: "Sezioni di censimento coinvolte",
      sections_losing_coverage: "Sezioni che perdono la copertura",
      closed_roads: "Strade chiuse",
      facilities: "Stazioni",
      target_min: "Tempo obiettivo",
      target_source: "Fonte dell'obiettivo",
      service: "Servizio",
      minutes_before: "Minuti prima",
      minutes_after: "Minuti dopo",
      before: "Prima",
      after: "Dopo",
      hotspots: "Punti critici di allagamento",
      hotspots_count: "Punti critici trovati",
      hollows_modelled: "Conche modellate",
      sections: "Sezioni di censimento",
      sez_id: "Sezione",
      sensitive_sites: "Siti sensibili",
      official_damage_zones: "Zone di danno ufficiali",
      sewer: "Fognatura",
      surcharge_points: "Punti di tracimazione",
      surcharge_m3: "Volume tracimato",
      surcharge_map_p50: "Area di tracimazione delle fognature (P50)",
      outfalls_blocked: "Scarichi bloccati dal fiume",
      outfalls_considered: "Scarichi considerati",
      efficiency: "Efficienza degli scarichi",
      street_drain_rate_mm_h: "Portata dei tombini",
      mean_m3: "Tracimazione media",
      max_depth_m: "Profondità massima",
      flooded_m2: "Area allagata",
      rain_mm_mean: "Pioggia media",
      probability_over_30cm: "Probabilità di oltre 30 cm",
      duration_h: "Durata",
      total_depth_index: "Indice di profondità totale",
      members: "Membri dell'insieme",
      model: "Modello",
      calibration: "Calibrazione",
      probability: "Probabilità",
      site: "Sito del rilascio",
      substance: "Sostanza",
      release_kg_s: "Portata del rilascio",
      wind: "Vento",
      speed_ms: "Velocità",
      from_deg: "Da",
      threshold_mg_m3: "Soglia",
      meaning: "Significato",
      area_km2: "Area",
      max_distance_m: "Distanza massima oltre la soglia",
      footprint_p50: "Estensione probabile (P50)",
      footprint_p95: "Estensione possibile (P95)",
      hot_map_p50: "Area calda (P50)",
      footprint_possible: "Zona possibile",
      impervious_pct: "Suolo impermeabile",
      tree_cover_pct: "Verde",
      tmax_c: "Massima di giorno",
      tmin_c: "Minima di notte",
      by_category: "Per categoria",
      count: "Conteggio",
      name: "Nome",
      category: "Categoria",
      subtype: "Tipo",
      day: "Giorno",
    } as Record<string, string>,
    affected: {
      "residents.residents": "Residenti nell'area interessata",
      "residents.children_0_14": "Bambini (0-14) nell'area interessata",
    } as Record<string, string>,
    notAvailable: "Non disponibile.",
    sameEveryRun: "uguale in ogni esecuzione del modello",
    range: (lo: string, hi: string) => `intervallo da ${lo} a ${hi}`,
    yes: "Sì",
    no: "No",
    middleEstimate: "stima centrale (P50)",
  },
});

const ACRONYMS: Record<string, string> = { aegl: "AEGL", idlh: "IDLH", osm: "OSM", sumo: "SUMO", acea: "ACEA", pgra: "PGRA" };

// Ordered longest first so "_mm_h" wins over "_h".
const UNITS: [string, string][] = [
  ["_mg_m3", "mg/m³"],
  ["_m3s", "m³/s"],
  ["_mm_h", "mm/h"],
  ["_kg_s", "kg/s"],
  ["_km2", "km²"],
  ["_m2", "m²"],
  ["_m3", "m³"],
  ["_ms", "m/s"],
  ["_deg", "°"],
  ["_pct", "%"],
  ["_mm", "mm"],
  ["_min", "min"],
  ["_c", "°C"],
  ["_m", "m"],
  ["_h", "h"],
  ["_s", "s"],
];

const GEOMETRY_TYPES = new Set(["Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point", "MultiPoint", "GeometryCollection", "Feature", "FeatureCollection"]);

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isPrimitive = (v: unknown) => v === null || ["string", "number", "boolean"].includes(typeof v);

export function isQuantile(v: unknown): v is Quantile {
  return isObj(v) && typeof v.p5 === "number" && typeof v.p50 === "number" && typeof v.p95 === "number";
}

function isGeometry(v: unknown): v is FootprintItem["geometry"] {
  return isObj(v) && typeof v.type === "string" && GEOMETRY_TYPES.has(v.type);
}

function isEmptyGeometry(g: FootprintItem["geometry"]): boolean {
  const o = g as Obj;
  if (Array.isArray(o.coordinates)) return o.coordinates.length === 0;
  if (Array.isArray(o.features)) return o.features.length === 0;
  return false;
}

/** "residents_cut_off" -> "Residents cut off". */
export function humanise(key: string): string {
  const words = key.split(/[_\s]+/).filter(Boolean).map((w) => ACRONYMS[w.toLowerCase()] ?? w);
  const s = words.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function unitKey(key: string): string {
  return key.replace(/_(p5|p50|p95|mean)$/, "");
}

/** Unit implied by a key's suffix (rise_m -> m), or "". */
export function unitFor(key: string): string {
  const k = unitKey(key);
  for (const [suffix, unit] of UNITS) if (k.endsWith(suffix) || k === suffix.slice(1)) return unit;
  return "";
}

function segmentLabel(seg: string): string {
  const dict = tr(T).dict;
  if (dict[seg]) return dict[seg];
  const k = unitKey(seg);
  for (const [suffix] of UNITS) if (k.endsWith(suffix) && k.length > suffix.length) return humanise(k.slice(0, -suffix.length));
  return humanise(seg);
}

/** Plain-English label for a dotted result path. */
export function labelFor(path: string): string {
  const dict = tr(T).dict;
  if (dict[path]) return dict[path];
  const segs = path.split(".");
  const kept = segs.length > 1 ? segs.filter((s) => !LABEL_SKIP.has(s)) : segs;
  const out: string[] = [];
  for (const p of (kept.length ? kept : segs).map(segmentLabel)) if (out[out.length - 1] !== p) out.push(p);
  return out.join(" · ");
}

/** Display rounding only: integers stay whole, others keep four significant figures. */
export function fmtNumber(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  if (Math.abs(v) >= 1000 || Number.isInteger(v)) return Math.round(v).toLocaleString(locale());
  const plain = String(Number(v.toPrecision(4)));
  return locale() === "it-IT" ? plain.replace(".", ",") : plain;
}

/** The range line under a figure. A range with no spread is said in words rather than as "x to x". */
export function rangeText(q: Pick<Quantile, "p5" | "p50" | "p95">): string {
  const t = tr(T);
  return q.p5 === q.p95 ? t.sameEveryRun : t.range(fmtNumber(q.p5), fmtNumber(q.p95));
}

const isProbabilityKey = (key: string) => /probab|chance/i.test(key);

/** One value as text. `key` gives the unit; `prob` formats 0..1 as a percentage. */
function fmtValue(key: string, v: unknown, prob = isProbabilityKey(key)): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (prob && v >= 0 && v <= 1) return `${Math.round(v * 100)}%`;
    const unit = unitFor(key);
    return unit ? `${fmtNumber(v)}${unit === "°" || unit === "%" ? "" : " "}${unit}` : fmtNumber(v);
  }
  if (typeof v === "boolean") return v ? tr(T).yes : tr(T).no;
  if (typeof v === "string") return v.replace(/_/g, " ");
  if (isQuantile(v)) {
    const unit = unitFor(key);
    return `${fmtNumber(v.p50)}${unit ? ` ${unit}` : ""} (${tr(T).range(fmtNumber(v.p5), fmtNumber(v.p95))})`;
  }
  if (Array.isArray(v)) return v.every(isPrimitive) ? v.map((x) => fmtValue(key, x, prob)).join(", ") : `${v.length}`;
  if (isObj(v)) {
    return Object.entries(v)
      .filter(([, x]) => x !== null && x !== undefined)
      .map(([k, x]) => `${segmentLabel(k)} ${fmtValue(k, x, prob || isProbabilityKey(k))}`)
      .join(" · ");
  }
  return String(v);
}

function levelOf(path: string): FootprintItem["level"] {
  const last = path.split(".").pop() ?? "";
  return /p95|possible/i.test(last) ? "possible" : "likely";
}

const ROW_KEY = "__row";

// The live service sorts keys alphabetically: put identifiers, then head counts, first.
const FIRST = [ROW_KEY, "name", "sez_id", "edge", "category", "subtype", "residents"];
const rank = (k: string) => {
  const i = FIRST.indexOf(k);
  return i < 0 ? FIRST.length : i;
};
function ordered<T>(entries: [string, T][]): [string, T][] {
  return [...entries].sort((a, b) => rank(a[0]) - rank(b[0]));
}

/** Nested flat objects (e.g. residents: {residents, children}) become dotted columns. */
function flattenRow(r: Obj): Obj {
  const out: Obj = {};
  for (const [k, v] of Object.entries(r)) {
    if (isObj(v) && !isQuantile(v) && !isGeometry(v) && Object.values(v).every(isPrimitive))
      for (const [sub, x] of Object.entries(v)) out[`${k}.${sub}`] = x;
    else out[k] = v;
  }
  return out;
}

function tableFrom(path: string, raw: Obj[], points: PlaceItem[]): TableItem {
  const label = labelFor(path);
  const rows = raw.map(flattenRow);
  const keys: string[] = [];
  for (const r of rows.slice(0, 20))
    for (const [k, v] of Object.entries(r)) {
      if (keys.includes(k) || k === "lon" || k === "lat" || isGeometry(v)) continue;
      // Deeper objects that are not ranges would not fit in a cell.
      if (isObj(v) && !isQuantile(v)) continue;
      keys.push(k);
    }
  // An internal road id says nothing to a reader once every row has its street name.
  const named = rows.every((r) => typeof r.name === "string" && r.name !== "");
  const cols = ordered(
    keys.filter((k) => !(named && k === "edge") && rows.some((r) => r[k] !== null && r[k] !== undefined)).map((k) => [k, k] as [string, string]),
  ).map(([k]) => k);
  const columns = cols.map((k) => {
    if (k === ROW_KEY) return "";
    const last = k.split(".").pop() ?? k;
    const unit = unitFor(last);
    const name = labelFor(k);
    return unit && unit !== "°" ? `${name} (${unit})` : name;
  });
  const cell = (k: string, v: unknown) => {
    if (typeof v === "number" && !isProbabilityKey(k)) return fmtNumber(v);
    if (isQuantile(v)) return `${fmtNumber(v.p50)} (${fmtNumber(v.p5)}–${fmtNumber(v.p95)})`;
    if (Array.isArray(v)) return String(v.length);
    return fmtValue(k, v);
  };
  for (const r of rows) {
    if (points.length >= MAX_POINTS) break;
    // Only real coordinates are drawn: an engine may put its own network metres in lon/lat.
    if (typeof r.lon === "number" && typeof r.lat === "number" && inRome(r.lon, r.lat)) {
      const name = r.name ?? r.sez_id ?? r.edge;
      points.push({ lon: r.lon, lat: r.lat, label: typeof name === "string" && name ? name : label, table: label });
    }
  }
  return { path, label, columns, rows: rows.slice(0, MAX_ROWS).map((r) => cols.map((k) => cell(k, r[k]))), total: rows.length };
}

/** {P1: {...}, P2: {...}}: two or more like objects holding only flat values read best as a table. */
function isKeyedRows(v: Obj): boolean {
  const vals = Object.values(v);
  return (
    vals.length >= 2 &&
    vals.every(
      (r) =>
        isObj(r) &&
        !isQuantile(r) &&
        !isGeometry(r) &&
        Object.values(r).every((x) => isPrimitive(x) || isQuantile(x) || (isObj(x) && !isGeometry(x) && Object.values(x).every(isPrimitive))),
    )
  );
}

/** Top-level head counts are people inside the modelled footprint: say so. */

export function summariseScenario(input: unknown): ScenarioSummary {
  const out: ScenarioSummary = { compare: null, comparisons: [], quantiles: [], facts: [], tables: [], footprints: [], points: [], notAvailable: null };
  if (!isObj(input)) return out;
  const result: Obj = { ...input };
  if (result.status === "not_available" || result.status === "refused") out.notAvailable = typeof result.reason === "string" ? result.reason : tr(T).notAvailable;
  const skip = new Set(TOP_SKIP);
  const pick = (x: Quantile): Quantile => ({ p5: x.p5, p50: x.p50, p95: x.p95 });
  if (isQuantile(result.baseline) && isQuantile(result.variant)) {
    out.compare = { baseline: pick(result.baseline), variant: pick(result.variant) };
    skip.add("baseline").add("variant");
  } else if (isObj(result.baseline) && isObj(result.variant)) {
    // Several measures, each for today and with the change (traffic): one row per measure, plain ones first.
    const b = result.baseline;
    const v = result.variant;
    const d = isObj(result.difference) ? result.difference : {};
    for (const k of Object.keys(b)) {
      const bk = b[k];
      const vk = v[k];
      const dk = d[k];
      if (isQuantile(bk) && isQuantile(vk))
        out.comparisons.push({ path: k, label: labelFor(k), unit: unitFor(k), baseline: pick(bk), variant: pick(vk), difference: isQuantile(dk) ? pick(dk) : null });
    }
    const rank = (c: ComparisonRow) => {
      const i = COMPARISON_ORDER.indexOf(c.path);
      return i < 0 ? COMPARISON_ORDER.length : i;
    };
    out.comparisons.sort((x, y) => rank(x) - rank(y));
    const first = out.comparisons[0];
    if (first) {
      out.compare = { baseline: first.baseline, variant: first.variant, label: first.label, path: first.path };
      skip.add("baseline").add("variant").add("difference");
    }
  } else {
    // No top-level pair: use the first nested one (e.g. residents_beyond_target in emergency access).
    const hit = Object.entries(result).find(([, v]) => isObj(v) && isQuantile(v.baseline) && isQuantile(v.variant));
    if (hit) {
      const [k, v] = hit as [string, { baseline: Quantile; variant: Quantile } & Obj];
      out.compare = { baseline: pick(v.baseline), variant: pick(v.variant), label: labelFor(k), path: k };
      const { baseline: _b, variant: _v, ...rest } = v;
      if (Object.keys(rest).length) result[k] = rest;
      else skip.add(k);
    }
  }

  const walk = (path: string, key: string, v: unknown): void => {
    if (v === null || v === undefined) return;
    if (isGeometry(v)) {
      if (!isEmptyGeometry(v)) out.footprints.push({ path, label: labelFor(path), level: levelOf(path), geometry: v });
      return;
    }
    if (isQuantile(v)) {
      out.quantiles.push({ path, label: labelFor(path), unit: unitFor(key), value: { p5: v.p5, p50: v.p50, p95: v.p95 } });
      return;
    }
    if (Array.isArray(v)) {
      if (v.length === 0) return;
      if (v.every(isObj)) out.tables.push(tableFrom(path, v, out.points));
      else if (v.every(isPrimitive)) out.facts.push({ path, label: labelFor(path), value: fmtValue(key, v) });
      return;
    }
    if (isObj(v)) {
      // {p5: {...}, p50: {...}, p95: {...}}: counts per footprint quantile, read as one range per count.
      if (isObj(v.p5) && isObj(v.p50) && isObj(v.p95)) {
        const lo = v.p5;
        const mid = v.p50;
        const hi = v.p95;
        for (const [k, m] of ordered(Object.entries(mid)))
          if (typeof m === "number" && typeof lo[k] === "number" && typeof hi[k] === "number")
            out.quantiles.push({ path: `${path}.${k}`, label: labelFor(`${path}.${k}`), unit: unitFor(k), value: { p5: lo[k], p50: m, p95: hi[k] } });
        for (const [k, x] of Object.entries(v)) if (!["p5", "p50", "p95"].includes(k)) walk(`${path}.${k}`, k, x);
        return;
      }
      const entries = Object.entries(v).filter(([, x]) => x !== null && x !== undefined);
      if (entries.length === 0) return;
      // {p50: {...}} alone: counts for the middle footprint only. Each is a figure, flagged as having no range.
      if (entries.length === 1 && isObj(v.p50) && Object.values(v.p50).every(isPrimitive)) {
        for (const [k, x] of ordered(Object.entries(v.p50)))
          if (typeof x === "number")
            out.facts.push({ path: `${path}.p50.${k}`, label: tr(T).affected[`${path}.${k}`] ?? labelFor(`${path}.${k}`), value: fmtValue(k, x), bare: fmtNumber(x), unit: unitFor(k), note: tr(T).middleEstimate });
        return;
      }
      if (entries.length <= 8 && entries.every(([, x]) => isPrimitive(x))) {
        out.facts.push({ path, label: labelFor(path), value: fmtValue(key, v) });
        return;
      }
      if (isKeyedRows(v)) {
        out.tables.push(tableFrom(path, entries.map(([k, x]) => ({ [ROW_KEY]: k, ...(x as Obj) })), out.points));
        return;
      }
      for (const [k, x] of ordered(entries)) walk(`${path}.${k}`, k, x);
      return;
    }
    if (typeof v === "number" && !isProbabilityKey(key)) out.facts.push({ path, label: labelFor(path), value: fmtValue(key, v), bare: fmtNumber(v), unit: unitFor(key) });
    else out.facts.push({ path, label: labelFor(path), value: fmtValue(key, v) });
  };

  for (const [k, v] of Object.entries(result)) if (!skip.has(k)) walk(k, k, v);
  return out;
}

/** What an officer asks first, in this order: people, the vulnerable, extent, counts of places. */
const KEY_RANK: RegExp[] = [
  /(^|\.)residents(_beyond_target|_cut_off|_newly_covered|_no_longer_hot)?$/,
  /children|elderly|aged_65|over_65/,
  /flooded_km2|hot_area_km2|area_km2\.(likely|possible)/,
  /hotspots_count|sensitive_sites\.count|closed_roads|sections_losing_coverage/,
];

/**
 * The few figures to show first. Ranked by KEY_RANK; model internals (sewer efficiency, depth index) stay below.
 * When nothing is ranked, the first ranges are used so the panel is never empty.
 */
export function keyFigures(s: ScenarioSummary, max = 4): KeyFigure[] {
  const all: KeyFigure[] = [
    ...s.quantiles.map((q) => ({ path: q.path, label: q.label, value: fmtNumber(q.value.p50), unit: q.unit, note: rangeText(q.value) })),
    ...s.facts.filter((f) => f.bare !== undefined && !f.path.startsWith("area.")).map((f) => ({ path: f.path, label: f.label, value: f.bare!, unit: f.unit ?? "", note: f.note })),
  ];
  const rank = (f: KeyFigure) => KEY_RANK.findIndex((r) => r.test(f.path.replace(/\.p50\./, ".")));
  const ranked = all
    .map((f, i) => ({ f, i, r: rank(f) }))
    .filter((x) => x.r >= 0)
    .sort((a, b) => a.r - b.r || a.i - b.i)
    .map((x) => x.f);
  return (ranked.length ? ranked : all.filter((f) => s.quantiles.some((q) => q.path === f.path))).slice(0, max);
}
