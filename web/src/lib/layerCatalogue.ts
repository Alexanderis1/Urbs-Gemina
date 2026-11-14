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
import { texts, tr } from "@/lib/i18n";

export type LayerGroup = "fused" | "fields" | "mobility" | "health" | "environment";

export interface LayerInfo {
  id: string;
  label: string;
  hint?: string;
  group: LayerGroup;
  icon: LucideIcon;
}

type LayerText = { label: string; hint?: string };

// Wording per layer id, staff and residents apart. Read at use time so it follows the language.
const STAFF_TEXT = texts<Record<string, LayerText>>({
  en: {
    air_no2: { label: "Air: NO₂", hint: "Stations + European model" },
    air_pm10: { label: "Air: PM10" },
    air_pm25: { label: "Air: PM2.5" },
    air_o3: { label: "Air: ozone" },
    road_speed: { label: "Road speed", hint: "Simulated loops + real buses" },
    transit_delay: { label: "Bus delay", hint: "Live bus feed" },
    rain: { label: "Rain", hint: "Radar + forecast" },
    air_temperature: { label: "Air temperature", hint: "Forecast + night heat island" },
    emf: { label: "Electric field", hint: "Cartoradio map + measurements" },
    activity: { label: "Street activity", hint: "Parked shared scooters, a weak proxy" },
    antenna_register: { label: "Antenna sites", hint: "Count per 500 m cell" },
    emf_baseline: { label: "EMF model points", hint: "Cartoradio grid" },
    traffic_flow: { label: "Traffic loops" },
    micromobility: { label: "Shared scooters and bikes" },
    hospitals: { label: "Hospitals" },
    schools_state: { label: "State schools" },
    air_quality: { label: "Air quality stations" },
    air_quality_model: { label: "Air quality model" },
    transit: { label: "Transit", hint: "Live buses" },
  },
  it: {
    air_no2: { label: "Aria: NO₂", hint: "Stazioni + modello europeo" },
    air_pm10: { label: "Aria: PM10" },
    air_pm25: { label: "Aria: PM2.5" },
    air_o3: { label: "Aria: ozono" },
    road_speed: { label: "Velocità su strada", hint: "Spire simulate + autobus reali" },
    transit_delay: { label: "Ritardo degli autobus", hint: "Dati live degli autobus" },
    rain: { label: "Pioggia", hint: "Radar + previsione" },
    air_temperature: { label: "Temperatura dell'aria", hint: "Previsione + isola di calore notturna" },
    emf: { label: "Campo elettrico", hint: "Mappa Cartoradio + misure" },
    activity: { label: "Attività in strada", hint: "Monopattini in condivisione in sosta, un indicatore debole" },
    antenna_register: { label: "Siti delle antenne", hint: "Conteggio per cella di 500 m" },
    emf_baseline: { label: "Punti del modello EMF", hint: "Griglia Cartoradio" },
    traffic_flow: { label: "Spire del traffico" },
    micromobility: { label: "Monopattini e bici in condivisione" },
    hospitals: { label: "Ospedali" },
    schools_state: { label: "Scuole statali" },
    air_quality: { label: "Stazioni di qualità dell'aria" },
    air_quality_model: { label: "Modello di qualità dell'aria" },
    transit: { label: "Trasporto pubblico", hint: "Autobus live" },
  },
});

const PUBLIC_TEXT = texts<Record<string, LayerText>>({
  en: {
    air_no2: { label: "Air: nitrogen dioxide (NO₂)", hint: "Monitoring stations and the European air model" },
    air_pm10: { label: "Air: dust (PM10)" },
    air_pm25: { label: "Air: fine dust (PM2.5)" },
    rain: { label: "Rain now", hint: "Weather radar and forecast" },
    air_temperature: { label: "Air temperature" },
    transit_delay: { label: "Bus delays", hint: "From the live bus feed" },
    hospitals: { label: "Hospitals" },
    schools_state: { label: "State schools" },
    micromobility: { label: "Shared scooters and bikes" },
    emf: { label: "Electric field from antennas", hint: "Estimate from the national antenna model" },
    antenna_register: { label: "Mobile antennas", hint: "How many in each 500 m square" },
  },
  it: {
    air_no2: { label: "Aria: biossido di azoto (NO₂)", hint: "Stazioni di monitoraggio e modello europeo dell'aria" },
    air_pm10: { label: "Aria: polveri (PM10)" },
    air_pm25: { label: "Aria: polveri sottili (PM2.5)" },
    rain: { label: "Pioggia adesso", hint: "Radar meteo e previsione" },
    air_temperature: { label: "Temperatura dell'aria" },
    transit_delay: { label: "Ritardi degli autobus", hint: "Dai dati live degli autobus" },
    hospitals: { label: "Ospedali" },
    schools_state: { label: "Scuole statali" },
    micromobility: { label: "Monopattini e bici in condivisione" },
    emf: { label: "Campo elettrico delle antenne", hint: "Stima dal modello nazionale delle antenne" },
    antenna_register: { label: "Antenne di telefonia", hint: "Quante in ogni quadrato di 500 m" },
  },
});

const GROUP_TEXT = texts<Record<LayerGroup, LayerText>>({
  en: {
    fused: { label: "Live estimates (sensor fusion)", hint: "One value and its range for every 170 m cell." },
    fields: { label: "Antennas and fields" },
    mobility: { label: "Mobility" },
    health: { label: "Health and schools" },
    environment: { label: "Environment" },
  },
  it: {
    fused: { label: "Stime live (fusione di sensori)", hint: "Un valore e il suo intervallo per ogni cella di 170 m." },
    fields: { label: "Antenne e campi" },
    mobility: { label: "Mobilità" },
    health: { label: "Salute e scuole" },
    environment: { label: "Ambiente" },
  },
});

type Entry = [id: string, group: LayerGroup, icon: LucideIcon];

/** A layer whose label and hint are read from the table when asked for, so they follow the current language. */
function build(entries: Entry[], table: Record<"en" | "it", Record<string, LayerText>>): readonly LayerInfo[] {
  return entries.map(([id, group, icon]) => ({
    id,
    group,
    icon,
    get label() {
      return tr(table)[id]?.label ?? id;
    },
    get hint() {
      return tr(table)[id]?.hint;
    },
  }));
}

// Layer ids as the live query_layer knows them (twin/api). Labels are for people; caveats go in `hint`.
// "fused" layers are the twin's own estimate for every 170 m cell (config/beliefs.yaml): sensors + a starting map.
export const MAP_LAYERS: readonly LayerInfo[] = build(
  [
    ["air_no2", "fused", Wind],
    ["air_pm10", "fused", Wind],
    ["air_pm25", "fused", Wind],
    ["air_o3", "fused", Wind],
    ["road_speed", "fused", Gauge],
    ["transit_delay", "fused", Timer],
    ["rain", "fused", CloudRain],
    ["air_temperature", "fused", Thermometer],
    ["emf", "fused", Zap],
    ["activity", "fused", Activity],
    ["antenna_register", "fields", RadioTower],
    ["emf_baseline", "fields", Zap],
    ["traffic_flow", "mobility", Car],
    ["micromobility", "mobility", Bike],
    ["hospitals", "health", Hospital],
    ["schools_state", "health", School],
    ["air_quality", "environment", Wind],
    ["air_quality_model", "environment", LayersIcon],
    ["transit", "mobility", Bus],
  ],
  STAFF_TEXT,
);

export const GROUPS: readonly { id: LayerGroup; label: string; hint?: string }[] = (
  ["fused", "fields", "mobility", "health", "environment"] as const
).map((id) => ({
  id,
  get label() {
    return tr(GROUP_TEXT)[id].label;
  },
  get hint() {
    return tr(GROUP_TEXT)[id].hint;
  },
}));

/**
 * What residents can pick: a short list in plain words. Left out on purpose: raw model points, the simulated
 * traffic loops and the road-speed estimate built on them (simulated values are operator material), and the
 * scooter-count proxy. The service decides what a citizen may receive (aggregates only); this is the wording.
 */
export const PUBLIC_LAYERS: readonly LayerInfo[] = build(
  [
    ["air_no2", "fused", Wind],
    ["air_pm10", "fused", Wind],
    ["air_pm25", "fused", Wind],
    ["rain", "fused", CloudRain],
    ["air_temperature", "fused", Thermometer],
    ["transit_delay", "fused", Timer],
    ["hospitals", "health", Hospital],
    ["schools_state", "health", School],
    ["micromobility", "mobility", Bike],
    ["emf", "fused", Zap],
    ["antenna_register", "fields", RadioTower],
  ],
  PUBLIC_TEXT,
);

const BUILDINGS_ONLY = texts({ en: "Buildings only", it: "Solo edifici" });

/** The layers for an experience. Label and hint are in the current language each time they are read. */
export function layersFor(experience: Experience): readonly LayerInfo[] {
  return experience === "staff" ? MAP_LAYERS : PUBLIC_LAYERS;
}

/** The name on screen. A layer outside the catalogue (asked for by voice or chat) gets readable words. */
export function layerLabel(id: string | null, experience: Experience = "staff"): string {
  if (id === null) return tr(BUILDINGS_ONLY);
  return layersFor(experience).find((l) => l.id === id)?.label ?? MAP_LAYERS.find((l) => l.id === id)?.label ?? metricInfo(id).label;
}

/** Fused layers are the twin's own estimate for every 170 m cell (config/beliefs.yaml). */
export function isFused(id: string | null): boolean {
  return MAP_LAYERS.some((l) => l.id === id && l.group === "fused");
}
