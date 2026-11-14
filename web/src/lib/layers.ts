// Turns any query_layer result (belief, observations, aggregate, features) into one map-ready shape.
// Shapes follow the live tool API (twin/api, 13 Nov 2026).
import type { Area } from "@/lib/area";

export interface MapItem {
  h3?: string;
  position?: [number, number];
  value: number;
  /** Standard deviation (belief) or sigma (observation), in the value's unit. 0 when not given. */
  uncertainty: number;
  label?: string;
  synthetic?: boolean;
  p5?: number;
  p95?: number;
}

export interface MapData {
  kind: "hex" | "points";
  metric: string;
  unit: string;
  items: MapItem[];
  /** Aggregate cell size in metres (antenna counts), for drawing. */
  cellM?: number;
  calibration?: string;
  method?: string;
  truncated?: boolean;
  count?: number;
}

/** Which value to colour by, per observation type. First match wins; otherwise the first numeric value. */
const MAIN_VALUE = ["intensity", "electricField", "precipitation", "pm10", "pm25", "pm2_5", "no2", "delay", "availableVehicles"];

/** Numeric fields that are flags for the tools, not readings to map. */
const FLAG_VALUES = new Set(["at_cap"]);

export interface MetricInfo {
  label: string;
  unit: string;
  /** What one dot stands for when every value is the same, e.g. "vehicle". */
  each?: string;
}

/**
 * Plain names and units of the values the tool returns.
 * Basis: FIWARE Smart Data Models (AirQualityObserved, TrafficFlowObserved); EEA stations and CAMS report µg/m³;
 * the Cartoradio grid is in V/m; the traffic loops give vehicles per hour (twin/providers/simulated/loops.py).
 */
const METRICS: Record<string, MetricInfo> = {
  no2: { label: "NO₂", unit: "µg/m³" },
  pm10: { label: "PM10", unit: "µg/m³" },
  pm25: { label: "PM2.5", unit: "µg/m³" },
  pm2_5: { label: "PM2.5", unit: "µg/m³" },
  o3: { label: "Ozone", unit: "µg/m³" },
  electricField: { label: "Electric field", unit: "V/m" },
  intensity: { label: "Traffic flow", unit: "vehicles/h" },
  averageVehicleSpeed: { label: "Average speed", unit: "km/h" },
  occupancy: { label: "Road occupancy", unit: "" },
  precipitation: { label: "Rain", unit: "" },
  availableVehicles: { label: "Vehicles available", unit: "", each: "vehicle" },
  rangeKm: { label: "Range left", unit: "km" },
  count: { label: "Count", unit: "" },
  // Fused layers (config/beliefs.yaml). Their unit comes with the answer, so none is written here.
  air_no2: { label: "NO₂", unit: "" },
  air_pm10: { label: "PM10", unit: "" },
  air_pm25: { label: "PM2.5", unit: "" },
  air_o3: { label: "Ozone", unit: "" },
  road_speed: { label: "Road speed", unit: "" },
  emf: { label: "Electric field", unit: "" },
  rain: { label: "Rain", unit: "" },
  temperature: { label: "Air temperature", unit: "" },
  air_temperature: { label: "Air temperature", unit: "" },
  activity: { label: "Shared scooters parked", unit: "" },
  transit_delay: { label: "Bus delay", unit: "" },
  transit_supply: { label: "Buses and trams planned", unit: "" },
  wifi_sessions: { label: "Wi-Fi sessions", unit: "" },
};

/** Units as the tools write them (plain ASCII), shown the way people read them. */
const UNITS: Record<string, string> = { "ug/m3": "µg/m³", degC: "°C", "vehicles/cell": "per cell", "sessions/hour": "per hour" };

export function prettyUnit(unit: string): string {
  return UNITS[unit] ?? unit;
}

/** The box of the area a tool answered for, to frame the map. Null for the whole city (the map already shows it). */
export function areaBounds(result: unknown): [[number, number], [number, number]] | null {
  const area = isObj(result) && isObj(result.area) ? result.area : null;
  if (!area || area.kind === "city" || !Array.isArray(area.bbox) || area.bbox.length !== 4) return null;
  const [w, s, e, n] = area.bbox.map(num);
  if (w === undefined || s === undefined || e === undefined || n === undefined) return null;
  return [
    [w, s],
    [e, n],
  ];
}

/**
 * Fused layers have one value for every 170 m cell, about 25,000 over Rome: too many for one answer.
 * Picked on the whole city they open on the centre (Municipio I); any other area is kept.
 */
export function areaForLayer(fused: boolean, area: Area): Area {
  return fused && area.type === "city" ? { type: "municipio", id: "1" } : area;
}

/** A refusal can carry a long list after its first sentence (every known layer name): keep the sentence. */
export function firstSentence(text: string): string {
  const end = text.indexOf(". ");
  return end < 0 ? text : text.slice(0, end + 1);
}

export function metricInfo(metric: string): MetricInfo {
  const known = METRICS[metric];
  if (known) return known;
  const words = metric
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase();
  return { label: words.charAt(0).toUpperCase() + words.slice(1), unit: "" };
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

/** Every numeric value the observations of a layer carry, the usual one first. Empty for other result types. */
export function availableMetrics(result: unknown): string[] {
  const r = isObj(result) ? result : {};
  if (r.type !== "observations" || !Array.isArray(r.observations)) return [];
  const first = r.observations.filter(isObj).find((o) => isObj(o.values));
  const values = first && isObj(first.values) ? first.values : {};
  const keys = Object.keys(values).filter((k) => num(values[k]) !== undefined && !FLAG_VALUES.has(k));
  const rank = (k: string) => {
    const i = MAIN_VALUE.indexOf(k);
    return i < 0 ? MAIN_VALUE.length : i;
  };
  return [...keys].sort((a, b) => rank(a) - rank(b));
}

/** `prefer` is the value the operator picked, used when the layer has it. */
export function normalizeLayer(result: unknown, prefer?: string): MapData {
  const r = isObj(result) ? result : {};
  const type = r.type;
  if (type === "belief" && Array.isArray(r.cells)) {
    return {
      kind: "hex",
      metric: String(r.layer ?? "value"),
      unit: prettyUnit(String(r.unit ?? "")),
      truncated: r.truncated === true,
      count: num(r.count),
      calibration: typeof r.calibration === "string" ? r.calibration : undefined,
      method: typeof r.method === "string" ? r.method : undefined,
      items: r.cells.filter(isObj).map((c) => ({
        h3: String(c.cell),
        value: num(c.mean) ?? num(c.p50) ?? 0,
        uncertainty: num(c.sd) ?? 0,
        p5: num(c.p5),
        p95: num(c.p95),
      })),
    };
  }
  if (type === "observations" && Array.isArray(r.observations)) {
    const obs = r.observations.filter(isObj);
    const keys = availableMetrics(r);
    const metric = prefer && keys.includes(prefer) ? prefer : (keys[0] ?? "value");
    return {
      kind: "points",
      metric,
      unit: metricInfo(metric).unit,
      truncated: r.truncated === true,
      count: num(r.count),
      items: obs
        .filter((o) => num(o.lon) !== undefined && num(o.lat) !== undefined)
        .map((o) => ({
          position: [o.lon as number, o.lat as number],
          value: num(isObj(o.values) ? o.values[metric] : undefined) ?? 0,
          uncertainty: num(isObj(o.sigma) ? o.sigma[metric] : undefined) ?? 0,
          synthetic: o.synthetic === true,
          label: typeof o.id === "string" ? o.id.split(":").pop() : undefined,
        })),
    };
  }
  if (type === "aggregate" && Array.isArray(r.cells)) {
    return {
      kind: "points",
      metric: "count",
      unit: "",
      cellM: num(r.cell_m),
      count: num(r.total),
      items: r.cells.filter(isObj).map((c) => ({ position: [c.lon as number, c.lat as number], value: num(c.count) ?? 0, uncertainty: 0 })),
    };
  }
  if (type === "features" && isObj(r.features) && Array.isArray(r.features.features)) {
    const items: MapItem[] = [];
    for (const f of r.features.features.filter(isObj)) {
      const g = isObj(f.geometry) ? f.geometry : null;
      if (g?.type !== "Point" || !Array.isArray(g.coordinates)) continue;
      const [lon, lat] = g.coordinates as number[];
      const p = isObj(f.properties) ? f.properties : {};
      const label = [p.denominazione, p.name, p.nome].find((x) => typeof x === "string") as string | undefined;
      items.push({ position: [lon!, lat!], value: 1, uncertainty: 0, label });
    }
    return { kind: "points", metric: "site", unit: "", items, count: num(r.count) };
  }
  return { kind: "points", metric: "value", unit: "", items: [] };
}

const NUM = new Intl.NumberFormat("en-GB", { maximumSignificantDigits: 3 });

/** At most three significant digits, for legends and tooltips. The value itself is unchanged. */
export function formatValue(n: number): string {
  return NUM.format(n).replace(/^−/, "-");
}

/** Real minimum and maximum of what is on screen. */
export function valueExtent(items: Pick<MapItem, "value">[]): { min: number; max: number } | null {
  if (!items.length) return null;
  let min = Infinity;
  let max = -Infinity;
  for (const i of items) {
    if (i.value < min) min = i.value;
    if (i.value > max) max = i.value;
  }
  return { min, max };
}

/** How a point layer is drawn: one plain dot per record, dots sized by count, or dots coloured by value. */
export type PointStyle = "sites" | "sized" | "values";

export function pointStyle(data: Pick<MapData, "metric" | "items">): PointStyle {
  if (data.metric === "site") return "sites";
  if (data.metric === "count") return "sized";
  const e = valueExtent(data.items);
  // Every record has the same value (each scooter is one vehicle): a colour scale would say nothing.
  return e && e.min === e.max && data.items.length > 1 ? "sites" : "values";
}

/** The most dots that can each carry their value as text without covering the map. */
export const MAX_VALUE_LABELS = 40;

export function showValueLabels(data: Pick<MapData, "kind" | "metric" | "items">): boolean {
  return data.kind === "points" && data.items.length > 0 && data.items.length <= MAX_VALUE_LABELS && pointStyle(data) === "values";
}

/** Smallest dot radius in pixels: a few sensors are drawn large, thousands of records small. */
export function dotRadiusPx(count: number): number {
  if (count <= 60) return 8;
  if (count <= 1000) return 5;
  return 4;
}

/** Hover text for one item: only the fields the tool returned. */
export function describeItem(item: MapItem, data: Pick<MapData, "metric" | "unit">): { title?: string; lines: string[]; synthetic: boolean } {
  const u = data.unit ? ` ${data.unit}` : "";
  const synthetic = item.synthetic === true;
  if (data.metric === "site") return { title: item.label, lines: [], synthetic };
  const lines = [`${metricInfo(data.metric).label}: ${formatValue(item.value)}${u}`];
  if (item.p5 !== undefined && item.p95 !== undefined) lines.push(`Range ${formatValue(item.p5)} to ${formatValue(item.p95)}${u}`);
  if (item.uncertainty > 0) lines.push(`Uncertainty ± ${formatValue(item.uncertainty)}${u}`);
  return { title: item.label, lines, synthetic };
}
