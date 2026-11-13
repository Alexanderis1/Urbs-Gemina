// Turns any query_layer result (belief, observations, aggregate, features) into one map-ready shape.
// Shapes follow the live tool API (twin/api, 13 Nov 2026).

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
const MAIN_VALUE = ["intensity", "electricField", "precipitation", "pm10", "pm2_5", "no2", "delay", "availableVehicles"];

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

export function normalizeLayer(result: unknown): MapData {
  const r = isObj(result) ? result : {};
  const type = r.type;
  if (type === "belief" && Array.isArray(r.cells)) {
    return {
      kind: "hex",
      metric: String(r.layer ?? "value"),
      unit: String(r.unit ?? ""),
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
    const first = obs.find((o) => isObj(o.values));
    const keys = first && isObj(first.values) ? Object.keys(first.values) : [];
    const metric = MAIN_VALUE.find((k) => keys.includes(k)) ?? keys.find((k) => num((first!.values as Record<string, unknown>)[k]) !== undefined) ?? "value";
    return {
      kind: "points",
      metric,
      unit: "",
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
