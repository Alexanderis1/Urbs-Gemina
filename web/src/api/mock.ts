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
  return polygonToCells(SAMPLE_RING, 8).map((h3) => {
    const [lat, lon] = cellToLatLng(h3);
    const base = Math.sin(lat * 60 + phase) * Math.cos(lon * 45 - phase);
    const centre = Math.exp(-(((lat - 41.9) / 0.05) ** 2 + ((lon - 12.49) / 0.06) ** 2));
    return { h3, mean: r1(0.5 + 0.3 * base + 0.6 * centre), variance: r1(0.02 + 0.2 * rnd() * (1 - centre)), updated_at: NOW };
  });
}

function result(tool: ToolName, inputs: Record<string, unknown>): Record<string, unknown> {
  const rnd = seeded(JSON.stringify(inputs) + tool);
  switch (tool) {
    case "resolve_place":
      if (typeof inputs.lat === "number" && typeof inputs.lon === "number")
        return { label: `Point ${inputs.lat.toFixed(5)}, ${inputs.lon.toFixed(5)}`, lat: inputs.lat, lon: inputs.lon };
      return { label: String(inputs.query ?? "Piazza Venezia, Roma"), lat: 41.8959, lon: 12.4823, municipio: "1" };
    case "context_check": {
      const cats = ["school", "hospital", "care home", "playground", "heritage constraint", "existing antenna site"];
      const kindOf = (c: string) => (c === "existing antenna site" ? "estimated" : "real");
      const pt = Array.isArray(inputs.point) ? (inputs.point as unknown[]) : [];
      const lon0 = num(pt[0], 12.4823);
      const lat0 = num(pt[1], 41.8959);
      const items = cats.map((category, i) => {
        const d = Math.round(40 + rnd() * 250);
        const bearing = rnd() * 2 * Math.PI;
        return {
          category,
          name: `Sample ${category} ${i + 1}`,
          distance_m: d,
          data_kind: kindOf(category),
          lat: lat0 + (d * Math.cos(bearing)) / 111_320,
          lon: lon0 + (d * Math.sin(bearing)) / (111_320 * Math.cos((lat0 * Math.PI) / 180)),
        };
      });
      return {
        radius_m: num(inputs.radius_m, 300),
        items: items.sort((a, b) => a.distance_m - b.distance_m),
        note: "Distances are context for the officer, not a prohibition.",
      };
    }
    case "estimate_field": {
      const p50 = r1(0.5 + rnd() * 2);
      return {
        unit: "V/m",
        estimate: { p5: r1(p50 * 0.4), p50, p95: r1(p50 * 2.6), calibration: "uncalibrated" },
        exceedance_probability: r1(rnd() * 0.05),
        threshold_ref: "attention value (config/thresholds.yaml)",
      };
    }
    case "query_layer": {
      const layer = String(inputs.layer ?? "air_quality");
      return { layer, unit: "index", cells: sampleCells(layer) };
    }
    case "run_scenario": {
      const b = r1(1 + rnd());
      const v = r1(b * (1.1 + rnd() * 0.5));
      return {
        kind: String(inputs.kind ?? "antenna_add"),
        metric: "residents above sample level",
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
          ["3D buildings (G0)", "OSM / Overture + GlobalBuildingAtlas heights", "estimated"],
          ["Context layers (schools, hospitals...)", "Roma Capitale GeoServer", "real"],
          ["Antenna sites", "OpenCelliD + OSM, power from Cartoradio", "estimated"],
          ["EMF field", "Cartoradio + twin model", "estimated"],
          ["Traffic loops", "sim_loops", "simulated"],
          ["Air quality", "EEA stations + model", "estimated"],
          ["Transit delay", "Roma GTFS-RT", "real"],
        ].map(([layer, provider, kind]) => ({
          layer,
          kind,
          provider: `${provider} (sample)`,
          licence: "n/a",
          last_update: NOW,
          validation: "not run in sample mode",
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
      const layer = String(inputs.layer ?? "air_quality");
      if (layer === "road_speed") return { road_speed: "estimated", traffic_loops: "simulated" };
      if (layer === "rain" || layer === "transit_delay") return { [layer]: "real" };
      return { [layer]: "estimated" };
    }
    case "run_scenario": {
      const k: Kinds = { what_if: "simulated", baseline: "estimated" };
      if (inputs.kind === "road_closure") k.traffic_loops = "simulated";
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
