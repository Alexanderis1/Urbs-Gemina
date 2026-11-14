// Mirrors the shared "tool response envelope" contract (plan/workstreams.md, shared interface 3).
// Do not change these shapes here: contract changes go through the design hub.

// "hypothetical" (added 14 Nov): an input the user made up for a what-if, e.g. a river level. Shown as WHAT-IF.
export const DATA_KINDS = ["real", "estimated", "simulated", "not_available", "hypothetical"] as const;
export type DataKind = (typeof DATA_KINDS)[number];

export const STATUSES = ["ok", "not_available", "refused"] as const;
export type ToolStatus = (typeof STATUSES)[number];

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
  /** Missing for static layers that carry no download time (allowed since 14 Nov). */
  retrieved_at?: string;
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
  /** Added 13 Nov: "ok" when absent. "refused" = guardrail (e.g. heavy run on too large an area). */
  status?: ToolStatus;
  reason?: string;
  cached?: boolean;
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

// --- Result shapes the UI reads, as returned by the live tool API (twin/api, 13 Nov 2026). ---

export type { ContextResult as ContextCheckResult } from "@/lib/context";

export interface AreaRef {
  status: string;
  id?: string;
  name?: string;
}

export interface ResolvePlaceResult {
  found: boolean;
  lon: number;
  lat: number;
  label?: string;
  precision?: string;
  method?: string;
  municipio?: AreaRef | null;
  urban_zone?: AreaRef | null;
  alternatives?: { lon: number; lat: number; label: string }[];
}

export interface ThresholdCheck {
  threshold_v_per_m?: number;
  source?: string;
  applies_to?: string;
  probability?: number;
}

/** estimate_field in point mode. */
export interface EstimateFieldResult {
  mode: "point" | "area";
  unit: string;
  p5: number;
  p50: number;
  p95: number;
  calibration: "calibrated" | "uncalibrated";
  model?: string;
  averaging_note?: string;
  exceedance?: Record<string, ThresholdCheck>;
  baseline?: { value_v_per_m?: number; credit?: string };
}

/** query_layer: one of belief / observations / aggregate / features; read it with lib/layers.normalizeLayer. */
export type QueryLayerResult = Record<string, unknown>;

export interface ScenarioResult {
  kind?: string;
  metric?: string;
  unit?: string;
  baseline?: Estimate;
  variant?: Estimate;
  /** Set inside the result when the engine could not run (e.g. no river cells in the area). */
  status?: string;
  reason?: string;
  model?: string;
  calibration?: string;
  [k: string]: unknown;
}

export interface LayerStatus {
  layer: string;
  provider: string;
  status: string;
  provider_kind?: string;
  synthetic?: boolean;
  licence?: string;
  cadence?: string;
  notes?: string;
  data_kind: DataKind;
  redistribution?: boolean;
}

export interface DataStatusResult {
  layers: LayerStatus[];
}
