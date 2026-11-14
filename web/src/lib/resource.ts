// What the hover card and the click card say about one thing on the map (a hospital, a sensor, a cell count).
// Only what the tool returned, in plain words. Contact details are never shown (no personal data).
import { texts, tr } from "@/lib/i18n";
import { formatValue, metricInfo, NAME_KEYS, type MapData, type MapItem } from "@/lib/layers";
import type { Glyph } from "@/map/markerGlyphs";

export interface ResourceFact {
  label: string;
  value: string;
  /** Set when the value is a web address. */
  href?: string;
}

export interface ResourceReading {
  label: string;
  value: string;
  unit: string;
  /** "± 1.65" or "5 to 12": how sure the reading is, when the tool says. */
  spread?: string;
}

export interface Resource {
  glyph: Glyph;
  title: string;
  category: string;
  /** The reading the map is coloured by. */
  main?: ResourceReading;
  readings: ResourceReading[];
  facts: ResourceFact[];
  /** Remaining fields as the source names them: shown to staff only. */
  extra: ResourceFact[];
  observedAt?: string;
  synthetic: boolean;
  position?: [number, number];
  id?: string;
}

const T = texts({
  en: {
    address: "Address",
    type: "Type",
    beds: "Beds",
    municipio: "Municipio",
    institute: "School group",
    website: "Website",
    place: "Place",
    range: (lo: string, hi: string) => `${lo} to ${hi}`,
    count: (n: string, things: string) => `${n} ${things}`,
    countIn: (m: string) => `Count in a ${m} m square`,
    cell: "Estimate for this cell",
    cellTitle: (label: string) => `${label} here`,
    category: {
      hospitals: "Hospital",
      schools_state: "School",
      air_quality: "Air quality station",
      air_quality_citizen: "Citizen air sensor",
      air_quality_model: "Air model point",
      traffic_flow: "Traffic sensor",
      micromobility: "Shared vehicle",
      transit: "Bus or tram",
      antenna_register: "Antenna site",
      emf_baseline: "Electric field point",
      emf_measurements: "Electric field measurement",
      health_care: "Health service",
      care_homes_osm: "Care home",
      playgrounds_osm: "Playground",
      nidi: "Nursery",
      infanzia: "Preschool",
    } as Record<string, string>,
    things: { antenna_register: "antenna sites" } as Record<string, string>,
    records: "records",
  },
  it: {
    address: "Indirizzo",
    type: "Tipo",
    beds: "Posti letto",
    municipio: "Municipio",
    institute: "Istituto comprensivo",
    website: "Sito web",
    place: "Luogo",
    range: (lo: string, hi: string) => `da ${lo} a ${hi}`,
    count: (n: string, things: string) => `${n} ${things}`,
    countIn: (m: string) => `Conteggio in un quadrato di ${m} m`,
    cell: "Stima per questa cella",
    cellTitle: (label: string) => `${label} qui`,
    category: {
      hospitals: "Ospedale",
      schools_state: "Scuola",
      air_quality: "Stazione di qualità dell'aria",
      air_quality_citizen: "Sensore d'aria dei cittadini",
      air_quality_model: "Punto del modello dell'aria",
      traffic_flow: "Sensore di traffico",
      micromobility: "Veicolo in condivisione",
      transit: "Autobus o tram",
      antenna_register: "Sito di antenne",
      emf_baseline: "Punto del campo elettrico",
      emf_measurements: "Misura del campo elettrico",
      health_care: "Servizio sanitario",
      care_homes_osm: "Casa di riposo",
      playgrounds_osm: "Area giochi",
      nidi: "Nido",
      infanzia: "Scuola dell'infanzia",
    } as Record<string, string>,
    things: { antenna_register: "siti di antenne" } as Record<string, string>,
    records: "elementi",
  },
});

const GLYPH: Record<string, Glyph> = {
  hospitals: "hospital",
  health_care: "care",
  care_homes_osm: "care",
  schools_state: "school",
  nidi: "play",
  infanzia: "school",
  playgrounds_osm: "play",
  air_quality: "air",
  air_quality_citizen: "air",
  air_quality_model: "air",
  air_no2: "air",
  air_pm10: "air",
  air_pm25: "air",
  air_o3: "air",
  air_temperature: "thermometer",
  traffic_flow: "traffic",
  road_speed: "traffic",
  micromobility: "scooter",
  activity: "scooter",
  transit: "bus",
  transit_delay: "bus",
  antenna_register: "antenna",
  masts_osm: "antenna",
  emf: "field",
  emf_baseline: "field",
  emf_measurements: "field",
  rain: "rain",
};

/** The glyph for a layer's markers. */
export function layerGlyph(layer: string | null): Glyph {
  return (layer && GLYPH[layer]) || "pin";
}

/** Field names that hold contact details: never shown, to anyone. */
const CONTACT = /mail|pec|tel|fax|cell|phone|contatt|referente|responsabile|dirigente/i;
/** Field names that only repeat the position or internal bookkeeping. */
const NOISE = /^(bbox|geom|geometr|fid|objectid|gid|id|lon|lat|x|y)$|_x$|_y$/i;

const str = (v: unknown): string | undefined => {
  if (typeof v === "string") return v.trim() || undefined;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return undefined;
};

/** "VIA MONTE ZEBIO 33" reads better as "Via Monte Zebio 33"; mixed-case text is left alone. */
function tidy(text: string): string {
  if (text !== text.toUpperCase() || text.length < 4) return text;
  return text.toLowerCase().replace(/(^|[\s.'(-])([a-zà-ù])/g, (_, a: string, b: string) => a + b.toUpperCase());
}

function placeFacts(p: Record<string, unknown>): { facts: ResourceFact[]; used: Set<string> } {
  const t = tr(T);
  const facts: ResourceFact[] = [];
  const used = new Set<string>(NAME_KEYS);
  const take = (keys: string[], label: string, map: (v: string) => string = tidy) => {
    for (const k of keys) {
      const v = str(p[k]);
      used.add(k);
      if (v) {
        facts.push({ label, value: map(v) });
        return;
      }
    }
  };
  take(["tipo_servizio", "tipologia", "TIPOLOGIA", "tipo", "category", "amenity"], t.type);
  const street = str(p.INDIRIZZO) ?? str(p.indirizzo) ?? str(p.address);
  const civic = str(p.OSP_NUMCIV) ?? str(p.civico);
  ["INDIRIZZO", "indirizzo", "address", "OSP_NUMCIV", "civico"].forEach((k) => used.add(k));
  if (street) facts.push({ label: t.address, value: tidy(civic && !street.includes(civic) ? `${street} ${civic}` : street) });
  take(["OSP_NLETTI", "posti_letto"], t.beds, (v) => v);
  take(["municipio", "MUNICIPIO"], t.municipio, (v) => v);
  take(["denominazione_istituto_comprensivo"], t.institute);
  for (const k of ["link_istituto_comprensivo", "website", "sito_web"]) {
    const v = str(p[k]);
    used.add(k);
    if (v) {
      facts.push({ label: t.website, value: v.replace(/^https?:\/\//, ""), href: /^https?:\/\//.test(v) ? v : `https://${v}` });
      break;
    }
  }
  return { facts, used };
}

function reading(metric: string, value: number, sigma?: number, p5?: number, p95?: number): ResourceReading {
  const info = metricInfo(metric);
  const spread =
    p5 !== undefined && p95 !== undefined ? tr(T).range(formatValue(p5), formatValue(p95)) : sigma && sigma > 0 ? `± ${formatValue(sigma)}` : undefined;
  return { label: info.label, value: formatValue(value), unit: info.unit, ...(spread ? { spread } : {}) };
}

/** Everything the cards show for one item of a layer. */
export function describeResource(item: MapItem, data: Pick<MapData, "kind" | "metric" | "unit" | "cellM">, layer: string | null): Resource {
  const t = tr(T);
  const glyph = layerGlyph(layer);
  const category = (layer && t.category[layer]) || t.place;
  const base = { glyph, synthetic: item.synthetic === true, position: item.position, id: item.id, observedAt: item.observedAt };

  // A cell of an estimated field (sensor fusion): one value with its range.
  if (data.kind === "hex") {
    const info = metricInfo(data.metric);
    const main: ResourceReading = { ...reading(data.metric, item.value, item.uncertainty, item.p5, item.p95), unit: data.unit || info.unit };
    return { ...base, title: t.cellTitle(info.label), category: t.cell, main, readings: [main], facts: [], extra: [] };
  }

  // A count per grid square (antenna sites for residents).
  if (data.metric === "count") {
    const things = (layer && t.things[layer]) || t.records;
    return {
      ...base,
      title: t.count(formatValue(item.value), things),
      category: data.cellM ? t.countIn(formatValue(data.cellM)) : category,
      readings: [],
      facts: [],
      extra: [],
    };
  }

  // A place from a register: name, type, address.
  if (item.props) {
    const p = item.props;
    const { facts, used } = placeFacts(p);
    const extra: ResourceFact[] = [];
    for (const [k, v] of Object.entries(p)) {
      const s = str(v);
      if (!s || used.has(k) || CONTACT.test(k) || NOISE.test(k)) continue;
      extra.push({ label: k, value: s });
    }
    const type = facts.find((f) => f.label === t.type)?.value;
    return { ...base, title: tidy(item.label ?? type ?? category), category, readings: [], facts, extra };
  }

  // A sensor: every value it reports, the mapped one first.
  const values = item.values ?? {};
  const keys = Object.keys(values);
  const order = [data.metric, ...keys.filter((k) => k !== data.metric)].filter((k) => k in values);
  const readings = order.map((k) => reading(k, values[k]!, item.sigmas?.[k]));
  const main = readings[0] ?? (data.metric !== "site" ? reading(data.metric, item.value, item.uncertainty) : undefined);
  const short = item.label?.replace(/^(eea-|sim-loop-|[a-z]+_gbfs-)/, "");
  return {
    ...base,
    title: short ? `${category} ${short}` : category,
    category,
    ...(main ? { main } : {}),
    readings: readings.length ? readings : main ? [main] : [],
    facts: [],
    extra: [],
  };
}
