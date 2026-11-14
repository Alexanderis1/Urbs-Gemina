// The layers the map can show, and how each experience names them (see lib/tiers.ts).
import {
  Activity,
  Bike,
  Bus,
  Car,
  CloudRain,
  Gauge,
  Hospital,
  Layers as LayersIcon,
  RadioTower,
  School,
  Thermometer,
  Timer,
  Wind,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { metricInfo } from "@/lib/layers";
import type { Experience } from "@/lib/tiers";

export type LayerGroup = "fused" | "fields" | "mobility" | "health" | "environment";

export interface LayerInfo {
  id: string;
  label: string;
  hint?: string;
  group: LayerGroup;
  icon: LucideIcon;
}

// Layer ids as the live query_layer knows them (twin/api). Labels are for people; caveats go in `hint`.
// "fused" layers are the twin's own estimate for every 170 m cell (config/beliefs.yaml): sensors + a starting map.
export const MAP_LAYERS: readonly LayerInfo[] = [
  { id: "air_no2", label: "Air: NO₂", hint: "Stations + European model", group: "fused", icon: Wind },
  { id: "air_pm10", label: "Air: PM10", group: "fused", icon: Wind },
  { id: "air_pm25", label: "Air: PM2.5", group: "fused", icon: Wind },
  { id: "air_o3", label: "Air: ozone", group: "fused", icon: Wind },
  { id: "road_speed", label: "Road speed", hint: "Simulated loops + real buses", group: "fused", icon: Gauge },
  { id: "transit_delay", label: "Bus delay", hint: "Live bus feed", group: "fused", icon: Timer },
  { id: "rain", label: "Rain", hint: "Radar + forecast", group: "fused", icon: CloudRain },
  { id: "air_temperature", label: "Air temperature", hint: "Forecast + night heat island", group: "fused", icon: Thermometer },
  { id: "emf", label: "Electric field", hint: "Cartoradio map + measurements", group: "fused", icon: Zap },
  { id: "activity", label: "Street activity", hint: "Parked shared scooters, a weak proxy", group: "fused", icon: Activity },
  { id: "antenna_register", label: "Antenna sites", hint: "Count per 500 m cell", group: "fields", icon: RadioTower },
  { id: "emf_baseline", label: "EMF model points", hint: "Cartoradio grid", group: "fields", icon: Zap },
  { id: "traffic_flow", label: "Traffic loops", group: "mobility", icon: Car },
  { id: "micromobility", label: "Shared scooters and bikes", group: "mobility", icon: Bike },
  { id: "hospitals", label: "Hospitals", group: "health", icon: Hospital },
  { id: "schools_state", label: "State schools", group: "health", icon: School },
  { id: "air_quality", label: "Air quality stations", group: "environment", icon: Wind },
  { id: "air_quality_model", label: "Air quality model", group: "environment", icon: LayersIcon },
  { id: "transit", label: "Transit", hint: "Live buses", group: "mobility", icon: Bus },
];

export const GROUPS: readonly { id: LayerGroup; label: string; hint?: string }[] = [
  { id: "fused", label: "Live estimates (sensor fusion)", hint: "One value and its range for every 170 m cell." },
  { id: "fields", label: "Antennas and fields" },
  { id: "mobility", label: "Mobility" },
  { id: "health", label: "Health and schools" },
  { id: "environment", label: "Environment" },
];

/**
 * What residents can pick: a short list in plain words. Left out on purpose: raw model points, the simulated
 * traffic loops and the road-speed estimate built on them (simulated values are operator material), and the
 * scooter-count proxy. The service decides what a citizen may receive (aggregates only); this is the wording.
 */
export const PUBLIC_LAYERS: readonly LayerInfo[] = [
  { id: "air_no2", label: "Air: nitrogen dioxide (NO₂)", hint: "Monitoring stations and the European air model", group: "fused", icon: Wind },
  { id: "air_pm10", label: "Air: dust (PM10)", group: "fused", icon: Wind },
  { id: "air_pm25", label: "Air: fine dust (PM2.5)", group: "fused", icon: Wind },
  { id: "rain", label: "Rain now", hint: "Weather radar and forecast", group: "fused", icon: CloudRain },
  { id: "air_temperature", label: "Air temperature", group: "fused", icon: Thermometer },
  { id: "transit_delay", label: "Bus delays", hint: "From the live bus feed", group: "fused", icon: Timer },
  { id: "hospitals", label: "Hospitals", group: "health", icon: Hospital },
  { id: "schools_state", label: "State schools", group: "health", icon: School },
  { id: "micromobility", label: "Shared scooters and bikes", group: "mobility", icon: Bike },
  { id: "emf", label: "Electric field from antennas", hint: "Estimate from the national antenna model", group: "fused", icon: Zap },
  { id: "antenna_register", label: "Mobile antennas", hint: "How many in each 500 m square", group: "fields", icon: RadioTower },
];

export function layersFor(experience: Experience): readonly LayerInfo[] {
  return experience === "staff" ? MAP_LAYERS : PUBLIC_LAYERS;
}

/** The name on screen. A layer outside the catalogue (asked for by voice or chat) gets readable words. */
export function layerLabel(id: string | null, experience: Experience = "staff"): string {
  if (id === null) return "Buildings only";
  return layersFor(experience).find((l) => l.id === id)?.label ?? MAP_LAYERS.find((l) => l.id === id)?.label ?? metricInfo(id).label;
}

/** Fused layers are the twin's own estimate for every 170 m cell (config/beliefs.yaml). */
export function isFused(id: string | null): boolean {
  return MAP_LAYERS.some((l) => l.id === id && l.group === "fused");
}
