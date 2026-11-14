// Scenario catalogue and change objects for run_scenario, in the shapes the scenario engine publishes
// (twin/scenarios/README.md, WS6). Note: add_antennas is estimate_field's variant shape, not run_scenario's.
import { texts, tr } from "@/lib/i18n";

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

const T = texts({
  en: {
    groups: { Water: "Water", Heat: "Heat", Hazard: "Hazard", Mobility: "Mobility", Antennas: "Antennas" } as Record<ScenarioGroup, string>,
    tiles: {
      river_flood: { label: "River flood", description: "The Tiber rises: which streets and people get wet." },
      rain_flood: { label: "Heavy rain and sewers", description: "A downpour fills hollows and overloads the drains." },
      heatwave: { label: "Heatwave", description: "Hot days and nights, and the effect of trees." },
      chemical_plume: { label: "Chemical release", description: "A toxic gas leak and who is downwind." },
      road_closure: { label: "Road closure or event", description: "Close a street, hold an event or open roadworks." },
      emergency_access: { label: "Emergency access", description: "How fast fire, police or ambulances still arrive." },
      antenna: { label: "New antenna", description: "Add a mast and estimate the field around it." },
      population_exposure: { label: "Population exposure", description: "Residents near a new mast, before and after." },
    } as Record<ScenarioTile, { label: string; description: string }>,
    gauges: { tevere_ripetta: "Tiber at Ripetta" } as Record<string, string>,
    services: { fire: "Fire brigade", ambulance: "Ambulance", police: "Police" } as Record<string, string>,
    longitude: "Longitude",
    latitude: "Latitude",
    height: "Height",
    gaugeLevel: "Gauge level",
    riverRise: "River rise",
    rain: "Rain",
    duration: "Duration",
    releaseRate: "Release rate",
    windSpeed: "Wind speed",
    windDirection: "Wind direction",
    dayMax: "Day maximum",
    nightMin: "Night minimum",
    treeCover: "Tree cover added",
    sealed: "Sealed ground removed",
    lanes: "Lanes closed",
    attendees: "Attendees",
    siteName: "Type the name of a hazardous site.",
    placeRelease: "Click the map to place the release point, or name a site.",
    substance: "Choose a substance.",
    streetName: "Type the name of the street.",
    number: (label: string) => `${label}: enter a number.`,
  },
  it: {
    groups: { Water: "Acqua", Heat: "Caldo", Hazard: "Rischio", Mobility: "Mobilità", Antennas: "Antenne" } as Record<ScenarioGroup, string>,
    tiles: {
      river_flood: { label: "Piena del fiume", description: "Il Tevere sale: quali strade e quante persone finiscono sott'acqua." },
      rain_flood: { label: "Pioggia intensa e fognature", description: "Un temporale riempie le conche e sovraccarica le fognature." },
      heatwave: { label: "Ondata di calore", description: "Giorni e notti calde, e l'effetto degli alberi." },
      chemical_plume: { label: "Rilascio chimico", description: "Una perdita di gas tossico e chi si trova sottovento." },
      road_closure: { label: "Chiusura stradale o evento", description: "Chiudi una strada, organizza un evento o apri un cantiere." },
      emergency_access: { label: "Accesso dei soccorsi", description: "Quanto in fretta arrivano ancora vigili del fuoco, polizia o ambulanze." },
      antenna: { label: "Nuova antenna", description: "Aggiungi un palo e stima il campo intorno." },
      population_exposure: { label: "Esposizione dei residenti", description: "Residenti vicino a un nuovo palo, prima e dopo." },
    } as Record<ScenarioTile, { label: string; description: string }>,
    gauges: { tevere_ripetta: "Tevere a Ripetta" } as Record<string, string>,
    services: { fire: "Vigili del fuoco", ambulance: "Ambulanza", police: "Polizia" } as Record<string, string>,
    longitude: "Longitudine",
    latitude: "Latitudine",
    height: "Altezza",
    gaugeLevel: "Livello all'idrometro",
    riverRise: "Aumento del fiume",
    rain: "Pioggia",
    duration: "Durata",
    releaseRate: "Portata del rilascio",
    windSpeed: "Velocità del vento",
    windDirection: "Direzione del vento",
    dayMax: "Massima di giorno",
    nightMin: "Minima di notte",
    treeCover: "Verde aggiunto",
    sealed: "Suolo impermeabile rimosso",
    lanes: "Corsie chiuse",
    attendees: "Partecipanti",
    siteName: "Scrivi il nome di un sito a rischio.",
    placeRelease: "Clicca sulla mappa per indicare il punto del rilascio, oppure scrivi il nome di un sito.",
    substance: "Scegli una sostanza.",
    streetName: "Scrivi il nome della strada.",
    number: (label: string) => `${label}: inserisci un numero.`,
  },
});

/** Display name of a scenario group, in the current language. */
export const groupLabel = (g: ScenarioGroup): string => tr(T).groups[g];

export const SCENARIO_BANDS = ["800", "900", "1800", "2100", "3500"] as const;
export const SCENARIO_GAUGES = [
  {
    id: "tevere_ripetta",
    get label() {
      return tr(T).gauges.tevere_ripetta!;
    },
  },
] as const;
export const SCENARIO_SUBSTANCES = ["ammonia", "chlorine"] as const;
export const SCENARIO_SERVICES = [
  {
    id: "fire",
    get label() {
      return tr(T).services.fire!;
    },
  },
  {
    id: "ambulance",
    get label() {
      return tr(T).services.ambulance!;
    },
  },
  {
    id: "police",
    get label() {
      return tr(T).services.police!;
    },
  },
] as const;

// The default antenna site is the one the lab always started from (Via Nazionale area).
const ANTENNA_SITE = { lat: "41.9009", lon: "12.4833", height_m: "30", band: "3500" };

export const SCENARIOS: readonly ScenarioSpec[] = [
  {
    id: "river_flood",
    get label() {
      return tr(T).tiles.river_flood.label;
    },
    get description() {
      return tr(T).tiles.river_flood.description;
    },
    group: "Water",
    // Default: the official 500-year flood (PGRA rare-flood map, P1). Today's river or a 3 m rise floods nothing,
    // and at 200 years the walls nearly hold, so the middle estimate in the centre can still be zero.
    defaults: { mode: "return", return_period: "500", rise_m: "3", gauge: "tevere_ripetta", level_m: "14" },
    usesPoint: false,
  },
  {
    id: "rain_flood",
    get label() {
      return tr(T).tiles.rain_flood.label;
    },
    get description() {
      return tr(T).tiles.rain_flood.description;
    },
    group: "Water",
    defaults: { mode: "rain", rain_mm: "60", duration_h: "1", river_rise_m: "" },
    usesPoint: false,
  },
  {
    id: "heatwave",
    get label() {
      return tr(T).tiles.heatwave.label;
    },
    get description() {
      return tr(T).tiles.heatwave.description;
    },
    group: "Heat",
    defaults: { temperature: "forecast", tmax_c: "36", tmin_c: "24", trees_pct: "", depave_pct: "" },
    usesPoint: false,
  },
  {
    id: "chemical_plume",
    get label() {
      return tr(T).tiles.chemical_plume.label;
    },
    get description() {
      return tr(T).tiles.chemical_plume.description;
    },
    group: "Hazard",
    defaults: { place: "point", site: "", lon: "", lat: "", substance: "ammonia", release_kg_s: "5", wind: "forecast", wind_speed_ms: "3", wind_from_deg: "270" },
    usesPoint: true,
  },
  {
    id: "road_closure",
    get label() {
      return tr(T).tiles.road_closure.label;
    },
    get description() {
      return tr(T).tiles.road_closure.description;
    },
    group: "Mobility",
    defaults: { mode: "close", street: "", attendees: "20000", lanes_closed: "1" },
    usesPoint: false,
  },
  {
    id: "emergency_access",
    get label() {
      return tr(T).tiles.emergency_access.label;
    },
    get description() {
      return tr(T).tiles.emergency_access.description;
    },
    group: "Mobility",
    defaults: { service: "fire", street: "", flood_rise_m: "" },
    usesPoint: false,
  },
  {
    id: "antenna",
    get label() {
      return tr(T).tiles.antenna.label;
    },
    get description() {
      return tr(T).tiles.antenna.description;
    },
    group: "Antennas",
    defaults: { ...ANTENNA_SITE },
    usesPoint: true,
  },
  {
    id: "population_exposure",
    get label() {
      return tr(T).tiles.population_exposure.label;
    },
    get description() {
      return tr(T).tiles.population_exposure.description;
    },
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
      if (f.mode === "return") return { gauge: "tevere_ripetta", return_period_years: n(f.return_period ?? "500") };
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
  const L = tr(T);
  // [key, label, required]
  switch (kind) {
    case "antenna":
    case "population_exposure":
      return [["lon", L.longitude, true], ["lat", L.latitude, true], ["height_m", L.height, false]];
    case "river_flood":
      return f.mode === "level" ? [["level_m", L.gaugeLevel, true]] : f.mode === "forecast" || f.mode === "return" ? [] : [["rise_m", L.riverRise, true]];
    case "rain_flood":
      return [
        ...(f.mode === "rain" || !f.mode ? ([["rain_mm", L.rain, true], ["duration_h", L.duration, true]] as [string, string, boolean][]) : []),
        ["river_rise_m", L.riverRise, false],
      ];
    case "chemical_plume":
      return [
        ...(f.place === "site" ? [] : ([["lon", L.longitude, true], ["lat", L.latitude, true]] as [string, string, boolean][])),
        ["release_kg_s", L.releaseRate, true],
        ...(f.wind === "manual" ? ([["wind_speed_ms", L.windSpeed, true], ["wind_from_deg", L.windDirection, true]] as [string, string, boolean][]) : []),
      ];
    case "emergency_access":
      return [["flood_rise_m", L.riverRise, false]];
    case "heatwave":
      return [
        ...(f.temperature === "manual" ? ([["tmax_c", L.dayMax, true], ["tmin_c", L.nightMin, false]] as [string, string, boolean][]) : []),
        ["trees_pct", L.treeCover, false],
        ["depave_pct", L.sealed, false],
      ];
    case "traffic_event":
      return f.mode === "roadworks" ? [["lanes_closed", L.lanes, true]] : [["attendees", L.attendees, true]];
    case "road_closure":
      return [];
  }
}

/** Plain-English reason the form cannot run yet, or null when it can. */
export function changeProblem(kind: ScenarioKind, f: Record<string, string>): string | null {
  const L = tr(T);
  if (kind === "chemical_plume") {
    if (f.place === "site" && !filled(f.site)) return L.siteName;
    if (f.place !== "site" && (!filled(f.lon) || !filled(f.lat))) return L.placeRelease;
    if (!filled(f.substance)) return L.substance;
  }
  if ((kind === "road_closure" || kind === "traffic_event" || kind === "emergency_access") && !street(f)) return L.streetName;
  for (const [key, label, required] of numberFields(kind, f)) {
    const v = f[key];
    if (!filled(v)) {
      if (required) return L.number(label);
      continue;
    }
    if (!Number.isFinite(Number(v))) return L.number(label);
  }
  return null;
}
