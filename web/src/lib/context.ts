import { getLang, texts, tr } from "@/lib/i18n";

const T = texts({
  en: { unnamed: "(unnamed)" },
  it: { unnamed: "(senza nome)" },
});

/**
 * Italian names of the layers the service checks (keys from config/context_layers.yaml). The service names them in
 * English; a layer not listed here keeps the service's own name.
 */
const LAYER_IT: Record<string, string> = {
  schools_state: "Scuole statali",
  nidi: "Asili nido comunali",
  infanzia: "Scuole dell'infanzia comunali",
  hospitals: "Ospedali",
  health_care: "Strutture sanitarie e assistenziali (Roma 241)",
  care_homes_osm: "RSA (OpenStreetMap)",
  playgrounds_osm: "Aree gioco (OpenStreetMap)",
  unesco: "Sito UNESCO Patrimonio dell'Umanità",
  unesco_buffer: "Zona cuscinetto UNESCO",
  protected_areas: "Aree protette",
  natura2000: "Siti Natura 2000",
  rete_ecologica_poly: "Rete ecologica (aree)",
  rete_ecologica_line: "Rete ecologica (linee)",
  cpq_morfologie: "Carta per la Qualità: morfologie urbane",
  cpq_preesistenze: "Carta per la Qualità: preesistenze archeologiche e storiche",
  cpq_spazi_aperti: "Carta per la Qualità: spazi aperti",
  cpq_edilizia_speciale: "Carta per la Qualità: edifici speciali",
  ptpr_paesaggi_roma: "PTPR Tavola A: sistemi di paesaggio",
  ptpr_a_aree_tutela_dm: "PTPR Tavola A: aree tutelate per decreto ministeriale",
  ptpr_b_ex_1497_ab: "PTPR Tavola B: bellezze panoramiche (ex L. 1497, a-b)",
  ptpr_b_ex_1497_cd: "PTPR Tavola B: bellezze panoramiche (ex L. 1497, c-d)",
  ptpr_b_boschi: "PTPR Tavola B: boschi",
  ptpr_b_acque_pubbliche: "PTPR Tavola B: acque pubbliche",
  ptpr_b_aree_archeologiche: "PTPR Tavola B: aree archeologiche",
  ptpr_b_decreti_archeologici: "PTPR Tavola B: decreti archeologici",
  ptpr_b_punti_archeologici: "PTPR Tavola B: punti archeologici",
  ptpr_b_centri_storici: "PTPR Tavola B: centri storici",
  ptpr_b_aree_naturali_protette: "PTPR Tavola B: aree naturali protette",
  ptpr_b_usi_civici: "PTPR Tavola B: usi civici",
  sitap_art136_ab: "Vincolo paesaggistico art. 136 a-b D.Lgs. 42/2004 (SITAP)",
  sitap_art136_cd: "Vincolo paesaggistico art. 136 c-d D.Lgs. 42/2004 (SITAP)",
  masts_osm: "Tralicci esistenti (OpenStreetMap)",
  prg_sistemi_regole: "PRG (Sistemi e Regole), campionato",
};

function layerName(l: { layer: string; label: string }): string {
  return getLang() === "it" ? (LAYER_IT[l.layer] ?? l.label) : l.label;
}

/** The service's "context only, not a prohibition" line (config/thresholds.yaml), in the current language. */
export function contextMeaning(meaning: string): string {
  if (getLang() !== "it" || !/not a prohibition/i.test(meaning)) return meaning;
  const source = /\(([^)]+)\)/.exec(meaning)?.[1];
  return `Solo informazioni di contesto, non un divieto${source ? ` (${source})` : ""}.`;
}

// Reads the live context_check result: groups -> layers -> hits.
export interface ContextHit {
  group: string;
  groupLabel: string;
  layer: string;
  layerLabel: string;
  name: string;
  distance_m: number;
}

export interface ContextLayer {
  layer: string;
  label: string;
  status: string;
  count?: number;
  hits?: { distance_m: number; name: string | null }[];
}

export interface ContextGroup {
  label: string;
  layers: ContextLayer[];
}

export interface ContextResult {
  point: { lon: number; lat: number };
  radius_m: number;
  meaning: string;
  groups: Record<string, ContextGroup>;
}

export function contextRows(result: unknown): ContextHit[] {
  const r = result as ContextResult;
  const rows: ContextHit[] = [];
  for (const [group, g] of Object.entries(r.groups ?? {}))
    for (const l of g.layers)
      for (const h of l.hits ?? [])
        rows.push({ group, groupLabel: g.label, layer: l.layer, layerLabel: layerName(l), name: h.name ?? tr(T).unnamed, distance_m: h.distance_m });
  return rows.sort((a, b) => a.distance_m - b.distance_m);
}

export function contextSummary(result: unknown) {
  const r = result as ContextResult;
  let notAvailable = 0;
  let sensitiveHits = 0;
  const unavailable: string[] = [];
  for (const [group, g] of Object.entries(r.groups ?? {}))
    for (const l of g.layers) {
      if (l.status !== "ok") {
        notAvailable++;
        unavailable.push(layerName(l));
      }
      if (group === "sensitive_site") sensitiveHits += l.count ?? 0;
    }
  return { notAvailable, sensitiveHits, unavailable };
}
