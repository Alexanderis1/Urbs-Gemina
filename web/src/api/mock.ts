// Sample-data mode: used when no tool API is configured, so the UI can be built and demoed
// before the back end is live. Data kinds mirror what the real tools will return under the
// project rule "only traffic loops are simulated" (plus hypothetical what-if inputs), and every
// response carries a "sample data" warning; the UI shows a SAMPLE marker on top of the kind.
// No legal threshold is produced here: thresholds only come from config/thresholds.yaml via the real tools.
import { polygonToCells, cellToLatLng } from "h3-js";
import type { Envelope, ToolName } from "./types";

const SAMPLE_WARNING = "Sample data: the tool API is not connected. Values are placeholders, not results.";
const NOW = "2026-11-13T12:00:00Z";
const SAMPLE_SOURCE = { id: "ui_sample_data", retrieved_at: NOW };

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Deterministic pseudo-random in [0,1) from a string seed. */
function seeded(seed: string): () => number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

const num = (v: unknown, d: number) => (typeof v === "number" ? v : d);
const r1 = (n: number) => Math.round(n * 100) / 100;

// Central Rome, roughly inside the GRA ring road, for sample hexagons.
const SAMPLE_RING: number[][] = [
  [41.98, 12.42], [41.99, 12.55], [41.92, 12.62], [41.83, 12.56], [41.82, 12.43], [41.88, 12.37], [41.98, 12.42],
];

function sampleCells(layer: string) {
  const rnd = seeded(layer);
  const phase = rnd() * 6;
  return polygonToCells(SAMPLE_RING, 8).map((cell) => {
    const [lat, lon] = cellToLatLng(cell);
    const base = Math.sin(lat * 60 + phase) * Math.cos(lon * 45 - phase);
    const centre = Math.exp(-(((lat - 41.9) / 0.05) ** 2 + ((lon - 12.49) / 0.06) ** 2));
    const mean = r1(0.5 + 0.3 * base + 0.6 * centre);
    const sd = r1(0.05 + 0.3 * rnd() * (1 - centre));
    return { cell, mean, sd, p5: r1(Math.max(0, mean - 1.645 * sd)), p50: mean, p95: r1(mean + 1.645 * sd), updated_at: NOW };
  });
}

const ctxLayer = (layer: string, label: string, hits: { distance_m: number; name: string }[]) => ({
  layer,
  label,
  status: "ok",
  count: hits.length,
  hits,
});

function result(tool: ToolName, inputs: Record<string, unknown>): Record<string, unknown> {
  const rnd = seeded(JSON.stringify(inputs) + tool);
  switch (tool) {
    case "resolve_place":
      return {
        found: true,
        label: String(inputs.text ?? "Piazza Venezia, Roma"),
        lon: 12.4823,
        lat: 41.8959,
        precision: "sample",
        method: "sample",
        municipio: { status: "ok", id: "1", name: "I" },
        urban_zone: { status: "ok", id: "1A", name: "Centro Storico" },
        alternatives: [],
      };
    case "context_check": {
      const pt = Array.isArray(inputs.point) ? (inputs.point as unknown[]) : [];
      const d = () => Math.round(40 + rnd() * 250);
      return {
        point: { lon: num(pt[0], 12.4823), lat: num(pt[1], 41.8959) },
        radius_m: num(inputs.radius_m, 300),
        meaning: "Context information only. Not a prohibition.",
        groups: {
          sensitive_site: {
            label: "Sensitive sites (schools, care, health, play areas)",
            layers: [
              ctxLayer("schools_state", "State schools", [{ distance_m: d(), name: "Sample school" }]),
              ctxLayer("hospitals", "Hospitals", []),
              ctxLayer("playgrounds_osm", "Playgrounds (OpenStreetMap)", [{ distance_m: d(), name: "Sample playground" }]),
            ],
          },
          constraint: {
            label: "Planning, landscape and heritage constraints",
            layers: [ctxLayer("unesco", "UNESCO World Heritage site", [{ distance_m: 0, name: "Sample heritage site" }])],
          },
        },
      };
    }
    case "estimate_field": {
      const p50 = r1(0.5 + rnd() * 2);
      // No threshold values here: they come only from config/thresholds.yaml through the real tool.
      return {
        mode: "point",
        unit: "V/m",
        p5: r1(p50 * 0.55),
        p50,
        p95: r1(p50 * 1.8),
        calibration: "uncalibrated",
        model: "sample",
        exceedance: { attention_value: { probability: 0, source: "config/thresholds.yaml (not loaded in sample mode)" } },
      };
    }
    case "query_layer": {
      const layer = String(inputs.layer ?? "rain");
      if (layer === "traffic_flow") {
        return {
          type: "observations",
          provider: "sim_loops",
          count: 20,
          truncated: false,
          observations: Array.from({ length: 20 }, (_, i) => ({
            id: `sample-loop-${i}`,
            lon: 12.42 + rnd() * 0.14,
            lat: 41.86 + rnd() * 0.08,
            observed_at: NOW,
            values: { intensity: Math.round(200 + rnd() * 800) },
            sigma: { intensity: 50 },
            synthetic: true,
          })),
        };
      }
      return { type: "belief", layer, unit: "index", calibration: "uncalibrated", cells: sampleCells(layer) };
    }
    case "run_scenario": {
      const b = r1(1 + rnd());
      const v = r1(b * (1.1 + rnd() * 0.5));
      return {
        kind: String(inputs.kind ?? "antenna"),
        metric: "residents in cells above the sample level",
        unit: "people",
        baseline: { p5: Math.round(b * 800), p50: Math.round(b * 1000), p95: Math.round(b * 1300), calibration: "uncalibrated" },
        variant: { p5: Math.round(v * 800), p50: Math.round(v * 1000), p95: Math.round(v * 1300), calibration: "uncalibrated" },
      };
    }
    case "legal_lookup":
      return { passages: [{ title: "Sample legal passage", quote: "Placeholder text. Connect the tool API for real citations.", url: "" }] };
    case "find_dataset":
      return { datasets: [{ id: "sample_dataset", title: "Sample dataset", url: "" }] };
    case "data_status":
      return {
        layers: [
          ["buildings_g0", "OSM / Overture + GlobalBuildingAtlas heights", "estimated"],
          ["context_layers", "Roma Capitale GeoServer", "real"],
          ["antenna_register", "OpenCelliD + OSM, power from Cartoradio", "estimated"],
          ["emf_baseline", "Cartoradio + twin model", "estimated"],
          ["traffic_flow", "sim_loops", "simulated"],
          ["air_quality", "EEA stations", "real"],
          ["transit", "Roma GTFS-RT", "real"],
          ["rain", "rain gauges + radar, fused", "estimated"],
        ].map(([layer, provider, kind]) => ({
          layer,
          provider: `${provider} (sample)`,
          status: "active",
          data_kind: kind,
          synthetic: kind === "simulated",
          licence: "n/a",
          cadence: "n/a",
          notes: "Sample mode: not validated.",
        })),
      };
  }
}

type Kinds = Record<string, "real" | "estimated" | "simulated">;

/** Data kinds per tool under the rule "only traffic loops are simulated". */
function kindsFor(tool: ToolName, inputs: Record<string, unknown>): Kinds {
  switch (tool) {
    case "resolve_place":
      return { geocoder: "real" };
    case "context_check":
      return { context_layers: "real", antenna_sites: "estimated" };
    case "estimate_field":
      return { emf_field: "estimated", antenna_sites: "estimated" };
    case "query_layer": {
      const layer = String(inputs.layer ?? "rain");
      if (layer === "traffic_flow") return { traffic_flow: "simulated" };
      if (["air_quality", "transit", "micromobility", "schools_state", "hospitals"].includes(layer)) return { [layer]: "real" };
      return { [layer]: "estimated" };
    }
    case "run_scenario": {
      const k: Kinds = { what_if: "simulated", baseline: "estimated" };
      if (inputs.kind === "road_closure") k.traffic_flow = "simulated";
      return k;
    }
    case "legal_lookup":
      return { legal_sources: "real" };
    case "find_dataset":
      return { catalogue: "real" };
    case "data_status":
      return { status: "real" };
  }
}

export async function mockTool(tool: ToolName, inputs: Record<string, unknown>): Promise<Envelope> {
  const run_id = await sha256(`${tool}|${JSON.stringify(inputs)}|sample-v2`);
  const data_kinds = kindsFor(tool, inputs);
  return {
    run_id,
    tool,
    inputs,
    result: result(tool, inputs),
    data_kinds,
    sources: [SAMPLE_SOURCE],
    synthetic: Object.values(data_kinds).includes("simulated"),
    warnings: [SAMPLE_WARNING],
    status: "ok",
    cached: false,
  };
}
