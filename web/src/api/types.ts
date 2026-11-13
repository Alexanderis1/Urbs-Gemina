// Mirrors the shared "tool response envelope" contract (plan/workstreams.md, shared interface 3).
// Do not change these shapes here: contract changes go through the design hub.

export const DATA_KINDS = ["real", "estimated", "simulated"] as const;
export type DataKind = (typeof DATA_KINDS)[number];

export const TOOL_NAMES = [
  "resolve_place",
  "context_check",
  "estimate_field",
  "query_layer",
  "run_scenario",
  "legal_lookup",
  "find_dataset",
  "data_status",
] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

export interface SourceRef {
  id: string;
  url?: string;
  retrieved_at: string;
}

export interface Envelope<R = unknown> {
  run_id: string;
  tool: string;
  inputs: Record<string, unknown>;
  result: R;
  data_kinds: Record<string, DataKind>;
  sources: SourceRef[];
  synthetic: boolean;
  warnings: string[];
}

export interface Estimate {
  p5: number;
  p50: number;
  p95: number;
  calibration: "calibrated" | "uncalibrated";
}

/** GeoJSON polygon as passed in the `area` argument. */
export interface PolygonGeometry {
  type: "Polygon";
  coordinates: number[][][];
}

// --- Result shapes the UI reads. Provisional until WS4 publishes twin/api/schemas/*.json. ---

export interface ResolvePlaceResult {
  label: string;
  lat: number;
  lon: number;
  municipio?: string;
}

export interface ContextItem {
  category: string;
  name: string;
  distance_m: number;
  data_kind: DataKind;
  lat?: number;
  lon?: number;
}

export interface ContextCheckResult {
  radius_m: number;
  items: ContextItem[];
  note: string;
}

export interface EstimateFieldResult {
  unit: string;
  estimate: Estimate;
  /** Probability of exceeding the attention value, computed by the tool from config/thresholds.yaml. */
  exceedance_probability?: number;
  threshold_ref?: string;
}

export interface LayerCell {
  h3: string;
  mean: number;
  variance: number;
  updated_at: string;
}

export interface QueryLayerResult {
  layer: string;
  unit: string;
  cells: LayerCell[];
}

export interface ScenarioResult {
  kind: string;
  metric: string;
  unit: string;
  baseline: Estimate;
  variant: Estimate;
}

export interface LayerStatus {
  layer: string;
  kind: DataKind;
  provider: string;
  licence: string;
  last_update: string;
  validation?: string;
}

export interface DataStatusResult {
  layers: LayerStatus[];
}
