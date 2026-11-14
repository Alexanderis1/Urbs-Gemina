// Ready-made use cases ("playbooks") published by the agents workstream: GET /use_cases lists the ones the
// caller's tier may run; POST /ask with `use_case` runs one and returns the usual TwinAnswer.
// The plan of tool calls is fixed on the server, so this file only describes and addresses them.
import type { Language, TwinQuestionBody } from "@/api/twin";
import { getLang } from "@/lib/i18n";
import { areaLabel, areaToArg, type Area, type AreaArg } from "./area";
import { humanise } from "./scenarioResult";
import type { Tier } from "./tiers";

export interface UseCase {
  id: string;
  title: Record<Language, string>;
  summary: Record<Language, string>;
  /** What the officer must give: an operating area or a place (address or name). */
  needs: ("area" | "place")[];
  /** Option name -> default (null = optional, no default). */
  params: Record<string, string | number | boolean | null>;
  /** Option name -> "text" | "number", when the server says (older servers do not). */
  paramTypes: Record<string, "text" | "number">;
  /** Plain labels of the tool steps, in the order the server runs them. */
  steps: string[];
  /** Who may run it. Only the sample list carries this; the live service sends each caller their own list. */
  tiers?: Tier[];
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function bilingual(v: unknown): Record<Language, string> | null {
  if (!isObj(v)) return null;
  const en = typeof v.en === "string" ? v.en : typeof v.it === "string" ? v.it : null;
  const it = typeof v.it === "string" ? v.it : en;
  return en && it ? { en, it } : null;
}

/** Tolerant reader: an entry that is not a use case is dropped, never guessed. */
export function parseUseCases(raw: unknown): UseCase[] {
  if (!Array.isArray(raw)) return [];
  const out: UseCase[] = [];
  for (const r of raw) {
    if (!isObj(r) || typeof r.id !== "string") continue;
    const title = bilingual(r.title);
    if (!title) continue;
    const params: UseCase["params"] = {};
    if (isObj(r.params))
      for (const [k, v] of Object.entries(r.params))
        if (v === null || typeof v === "string" || typeof v === "number" || typeof v === "boolean") params[k] = v;
    const paramTypes: UseCase["paramTypes"] = {};
    if (isObj(r.param_types))
      for (const [k, v] of Object.entries(r.param_types)) if (v === "text" || v === "number") paramTypes[k] = v;
    out.push({
      id: r.id,
      title,
      summary: bilingual(r.summary) ?? { en: "", it: "" },
      needs: (Array.isArray(r.needs) ? r.needs : []).filter((n): n is "area" | "place" => n === "area" || n === "place"),
      params,
      paramTypes,
      steps: (Array.isArray(r.steps) ? r.steps : []).filter((s): s is string => typeof s === "string"),
      ...(Array.isArray(r.tiers) ? { tiers: r.tiers.filter((t): t is Tier => t === "citizen" || t === "office") } : {}),
    });
  }
  return out;
}

/** The tasks one tier may run. A task without `tiers` is kept (the service has already filtered its list). */
export function forTier(list: UseCase[], tier: Tier): UseCase[] {
  return list.filter((u) => !u.tiers || u.tiers.includes(tier));
}

/** Titles on the residents' home page: the service names tasks for officers ("Citizen information about their area"). */
const RESIDENT_WORDING: Record<Language, Record<string, { title: string; summary: string }>> = {
  en: {
    citizen_area_info: { title: "Around my address", summary: "Air, rain, public transport, pharmacies and hospitals nearby, in plain words." },
    sport_deserts: { title: "Where sports facilities are missing", summary: "For one sport: who has a facility within walking distance, who does not, and the facilities that exist." },
    citizen_emergency_info: {
      title: "In an emergency near home",
      summary: "Where to gather, flood and landslide areas at your address, industrial zones and the nearest emergency hospitals.",
    },
  },
  it: {
    sport_deserts: { title: "Dove mancano gli impianti sportivi", summary: "Per uno sport: chi ha un impianto raggiungibile a piedi, chi no, e gli impianti che ci sono." },
    citizen_area_info: {
      title: "Intorno al mio indirizzo",
      summary: "Aria, pioggia, trasporto pubblico, farmacie e ospedali vicini, in parole semplici.",
    },
    citizen_emergency_info: {
      title: "In caso di emergenza vicino a casa",
      summary: "Dove ritrovarsi, aree a rischio alluvione e frana al tuo indirizzo, zone industriali e gli ospedali di emergenza più vicini.",
    },
  },
};

export function residentWording(uc: UseCase): { title: string; summary: string } {
  const lang = getLang();
  return RESIDENT_WORDING[lang][uc.id] ?? { title: uc.title[lang], summary: uc.summary[lang] };
}

export interface ParamField {
  key: string;
  label: string;
  unit: string;
  numeric: boolean;
  initial: string;
}

const UNIT_SUFFIX: [string, string][] = [
  ["_m", "m"],
  ["_h", "h"],
  ["_c", "°C"],
  ["_pct", "%"],
];

/** Form fields for a use case's options. The server's type wins; otherwise a null default is an optional number. */
export function paramFields(uc: UseCase): ParamField[] {
  return Object.entries(uc.params).map(([key, def]) => {
    const hit = UNIT_SUFFIX.find(([suffix]) => key.endsWith(suffix));
    return {
      key,
      label: humanise(hit ? key.slice(0, -hit[0].length) : key),
      unit: hit?.[1] ?? "",
      numeric: uc.paramTypes[key] ? uc.paramTypes[key] === "number" : def === null || typeof def === "number",
      initial: def === null ? "" : String(def),
    };
  });
}

export interface UseCaseInput {
  place: string;
  area: Area;
  values: Record<string, string>;
  language: Language;
  conversationId: string | null;
}

export type UseCaseQuestionBody = Omit<TwinQuestionBody, "area"> & {
  area: AreaArg | null;
  use_case: string;
  params: Record<string, string | number>;
};

const needsPlace = (uc: UseCase) => uc.needs.includes("place");

export function buildUseCaseQuestion(uc: UseCase, input: UseCaseInput): UseCaseQuestionBody {
  const params: Record<string, string | number> = {};
  // The service finds the place from params.place (the question text alone gives "place not found").
  if (needsPlace(uc) && input.place.trim()) params.place = input.place.trim();
  for (const f of paramFields(uc)) {
    const v = (input.values[f.key] ?? f.initial).trim();
    if (!v) continue;
    if (!f.numeric) params[f.key] = v;
    else if (Number.isFinite(Number(v))) params[f.key] = Number(v);
  }
  return {
    question: needsPlace(uc) ? input.place.trim() : `${uc.title[input.language]}: ${areaLabel(input.area)}`,
    language: input.language,
    area: uc.needs.includes("area") ? areaToArg(input.area) : null,
    mode: "question",
    conversation_id: input.conversationId,
    use_case: uc.id,
    params,
  };
}

/** How the request is shown in the conversation. */
export function useCaseTurnLabel(uc: UseCase, input: UseCaseInput): string {
  return `${uc.title[input.language]} · ${needsPlace(uc) ? input.place.trim() : areaLabel(input.area)}`;
}

/** True when the form has what the use case needs. */
export function useCaseReady(uc: UseCase, input: Pick<UseCaseInput, "place" | "area">): boolean {
  if (needsPlace(uc)) return input.place.trim().length > 0;
  return input.area.type !== "zone" || input.area.id.length > 0;
}
