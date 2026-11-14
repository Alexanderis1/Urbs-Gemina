// Scenario catalogue and change objects for run_scenario, in the shapes the scenario engine publishes
// (twin/scenarios/README.md, WS6). Note: add_antennas is estimate_field's variant shape, not run_scenario's.
export type ScenarioKind =
  | "antenna"
  | "population_exposure"
  | "road_closure"
  | "traffic_event"
  | "river_flood"
  | "rain_flood"
  | "chemical_plume"
  | "emergency_access"
  | "heatwave";

/** One tile in the lab. "road_closure" also covers traffic_event (public event, roadworks). */
export type ScenarioTile = Exclude<ScenarioKind, "traffic_event">;

export type ScenarioGroup = "Water" | "Heat" | "Hazard" | "Mobility" | "Antennas";

export interface ScenarioSpec {
  id: ScenarioTile;
  label: string;
  description: string;
  group: ScenarioGroup;
  /** Form values the officer starts from. All strings, as typed in the inputs. */
  defaults: Record<string, string>;
  /** The change needs a point that can be placed by clicking the map. */
  usesPoint: boolean;
}

export const SCENARIO_BANDS = ["800", "900", "1800", "2100", "3500"] as const;
export const SCENARIO_GAUGES = [{ id: "tevere_ripetta", label: "Tiber at Ripetta" }] as const;
export const SCENARIO_SUBSTANCES = ["ammonia", "chlorine"] as const;
export const SCENARIO_SERVICES = [
  { id: "fire", label: "Fire brigade" },
  { id: "ambulance", label: "Ambulance" },
  { id: "police", label: "Police" },
] as const;

// The default antenna site is the one the lab always started from (Via Nazionale area).
const ANTENNA_SITE = { lat: "41.9009", lon: "12.4833", height_m: "30", band: "3500" };

export const SCENARIOS: readonly ScenarioSpec[] = [
  {
    id: "river_flood",
    label: "River flood",
    description: "The Tiber rises: which streets and people get wet.",
    group: "Water",
    defaults: { mode: "rise", rise_m: "3", gauge: "tevere_ripetta", level_m: "14" },
    usesPoint: false,
  },
  {
    id: "rain_flood",
    label: "Heavy rain and sewers",
    description: "A downpour fills hollows and overloads the drains.",
    group: "Water",
    defaults: { mode: "rain", rain_mm: "60", duration_h: "1", river_rise_m: "" },
    usesPoint: false,
  },
  {
    id: "heatwave",
    label: "Heatwave",
    description: "Hot days and nights, and the effect of trees.",
    group: "Heat",
    defaults: { temperature: "forecast", tmax_c: "36", tmin_c: "24", trees_pct: "", depave_pct: "" },
    usesPoint: false,
  },
  {
    id: "chemical_plume",
    label: "Chemical release",
    description: "A toxic gas leak and who is downwind.",
    group: "Hazard",
    defaults: { place: "point", site: "", lon: "", lat: "", substance: "ammonia", release_kg_s: "5", wind: "forecast", wind_speed_ms: "3", wind_from_deg: "270" },
    usesPoint: true,
  },
  {
    id: "road_closure",
    label: "Road closure or event",
    description: "Close a street, hold an event or open roadworks.",
    group: "Mobility",
    defaults: { mode: "close", street: "", attendees: "20000", lanes_closed: "1" },
    usesPoint: false,
  },
  {
    id: "emergency_access",
    label: "Emergency access",
    description: "How fast fire, police or ambulances still arrive.",
    group: "Mobility",
    defaults: { service: "fire", street: "", flood_rise_m: "" },
    usesPoint: false,
  },
  {
    id: "antenna",
    label: "New antenna",
    description: "Add a mast and estimate the field around it.",
    group: "Antennas",
    defaults: { ...ANTENNA_SITE },
    usesPoint: true,
  },
  {
    id: "population_exposure",
    label: "Population exposure",
    description: "Residents near a new mast, before and after.",
    group: "Antennas",
    defaults: { ...ANTENNA_SITE },
    usesPoint: true,
  },
];

export const SCENARIO_GROUPS: readonly ScenarioGroup[] = ["Water", "Heat", "Hazard", "Mobility", "Antennas"];

export function scenarioSpec(id: ScenarioTile): ScenarioSpec {
  return SCENARIOS.find((s) => s.id === id)!;
}

/** The engine kind a tile and its form stand for. */
export function resolveKind(tile: ScenarioTile, f: Record<string, string>): ScenarioKind {
  if (tile === "road_closure" && (f.mode === "event" || f.mode === "roadworks")) return "traffic_event";
  return tile;
}

/** Heavy kinds run a network simulation and need a municipio, zone or drawn area. */
export function isHeavy(kind: ScenarioKind): boolean {
  return kind === "road_closure" || kind === "traffic_event" || kind === "emergency_access";
}

/** Traffic simulations only run on a few blocks; the tool refuses a larger area and says its limit. */
export function needsSmallArea(kind: ScenarioKind): boolean {
  return kind === "road_closure" || kind === "traffic_event";
}

const n = (v: string | undefined) => Number(v);
const filled = (v: string | undefined) => (v ?? "").trim() !== "";
const street = (f: Record<string, string>) => (f.street ?? "").trim();

function site(f: Record<string, string>): Record<string, unknown> {
  return {
    lon: Number(f.lon),
    lat: Number(f.lat),
    ...(f.height_m?.trim() ? { height_m: Number(f.height_m) } : {}),
    band: f.band ?? "3500",
  };
}

export function buildScenarioChange(kind: ScenarioKind, f: Record<string, string>): Record<string, unknown> {
  switch (kind) {
    case "antenna":
      return { action: "add", site: site(f) };
    case "population_exposure":
      return { site: site(f) };
    case "road_closure":
      return { close: { street: street(f) } };
    case "traffic_event":
      return f.mode === "roadworks"
        ? { roadworks: [{ street: street(f), lanes_closed: n(f.lanes_closed) }] }
        : { event: { street: street(f), attendees: n(f.attendees) } };
    case "river_flood":
      if (f.mode === "level") return { gauge: f.gauge ?? "tevere_ripetta", level_m: n(f.level_m) };
      if (f.mode === "forecast") return { gauge: f.gauge ?? "tevere_ripetta", forecast_day: "peak" };
      return { rise_m: n(f.rise_m) };
    case "rain_flood": {
      const base: Record<string, unknown> =
        f.mode === "radar" || f.mode === "forecast" ? { source: f.mode } : { rain_mm: n(f.rain_mm), duration_h: n(f.duration_h) };
      return filled(f.river_rise_m) ? { ...base, river: { rise_m: n(f.river_rise_m) } } : base;
    }
    case "chemical_plume": {
      const where = f.place === "site" ? { site: (f.site ?? "").trim() } : { lon: n(f.lon), lat: n(f.lat) };
      const wind = f.wind === "manual" ? { speed_ms: n(f.wind_speed_ms), from_deg: n(f.wind_from_deg) } : "forecast";
      return { ...where, substance: (f.substance ?? "").trim(), release_kg_s: n(f.release_kg_s), wind };
    }
    case "emergency_access": {
      const out: Record<string, unknown> = { service: f.service ?? "fire", close: { street: street(f) } };
      if (filled(f.flood_rise_m)) out.flood = { kind: "river_flood", change: { rise_m: n(f.flood_rise_m) } };
      return out;
    }
    case "heatwave": {
      const out: Record<string, unknown> =
        f.temperature === "manual" ? { tmax_c: n(f.tmax_c), ...(filled(f.tmin_c) ? { tmin_c: n(f.tmin_c) } : {}) } : { temperature: "forecast" };
      if (filled(f.trees_pct)) out.plant_trees = { cover_added_pct: n(f.trees_pct) };
      if (filled(f.depave_pct)) out.depave = { impervious_removed_pct: n(f.depave_pct) };
      return out;
    }
  }
}

/** Fields that must hold a number for this kind and form. Optional ones are checked only when filled. */
function numberFields(kind: ScenarioKind, f: Record<string, string>): [string, string, boolean][] {
  // [key, label, required]
  switch (kind) {
    case "antenna":
    case "population_exposure":
      return [["lon", "Longitude", true], ["lat", "Latitude", true], ["height_m", "Height", false]];
    case "river_flood":
      return f.mode === "level" ? [["level_m", "Gauge level", true]] : f.mode === "forecast" ? [] : [["rise_m", "River rise", true]];
    case "rain_flood":
      return [
        ...(f.mode === "rain" || !f.mode ? ([["rain_mm", "Rain", true], ["duration_h", "Duration", true]] as [string, string, boolean][]) : []),
        ["river_rise_m", "River rise", false],
      ];
    case "chemical_plume":
      return [
        ...(f.place === "site" ? [] : ([["lon", "Longitude", true], ["lat", "Latitude", true]] as [string, string, boolean][])),
        ["release_kg_s", "Release rate", true],
        ...(f.wind === "manual" ? ([["wind_speed_ms", "Wind speed", true], ["wind_from_deg", "Wind direction", true]] as [string, string, boolean][]) : []),
      ];
    case "emergency_access":
      return [["flood_rise_m", "River rise", false]];
    case "heatwave":
      return [
        ...(f.temperature === "manual" ? ([["tmax_c", "Day maximum", true], ["tmin_c", "Night minimum", false]] as [string, string, boolean][]) : []),
        ["trees_pct", "Tree cover added", false],
        ["depave_pct", "Sealed ground removed", false],
      ];
    case "traffic_event":
      return f.mode === "roadworks" ? [["lanes_closed", "Lanes closed", true]] : [["attendees", "Attendees", true]];
    case "road_closure":
      return [];
  }
}

/** Plain-English reason the form cannot run yet, or null when it can. */
export function changeProblem(kind: ScenarioKind, f: Record<string, string>): string | null {
  if (kind === "chemical_plume") {
    if (f.place === "site" && !filled(f.site)) return "Type the name of a hazardous site.";
    if (f.place !== "site" && (!filled(f.lon) || !filled(f.lat))) return "Click the map to place the release point, or name a site.";
    if (!filled(f.substance)) return "Choose a substance.";
  }
  if ((kind === "road_closure" || kind === "traffic_event" || kind === "emergency_access") && !street(f)) return "Type the name of the street.";
  for (const [key, label, required] of numberFields(kind, f)) {
    const v = f[key];
    if (!filled(v)) {
      if (required) return `${label}: enter a number.`;
      continue;
    }
    if (!Number.isFinite(Number(v))) return `${label}: enter a number.`;
  }
  return null;
}
