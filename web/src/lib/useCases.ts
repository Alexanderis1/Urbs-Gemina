// Ready-made use cases ("playbooks") published by the agents workstream: GET /use_cases lists the ones the
// caller's tier may run; POST /ask with `use_case` runs one and returns the usual TwinAnswer.
// The plan of tool calls is fixed on the server, so this file only describes and addresses them.
import type { Language, TwinQuestionBody } from "@/api/twin";
import { areaLabel, areaToArg, type Area, type AreaArg } from "./area";
import { humanise } from "./scenarioResult";

export interface UseCase {
  id: string;
  title: Record<Language, string>;
  summary: Record<Language, string>;
  /** What the officer must give: an operating area or a place (address or name). */
  needs: ("area" | "place")[];
  /** Option name -> default (null = optional, no default). */
  params: Record<string, string | number | boolean | null>;
  /** Plain labels of the tool steps, in the order the server runs them. */
  steps: string[];
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
    out.push({
      id: r.id,
      title,
      summary: bilingual(r.summary) ?? { en: "", it: "" },
      needs: (Array.isArray(r.needs) ? r.needs : []).filter((n): n is "area" | "place" => n === "area" || n === "place"),
      params,
      steps: (Array.isArray(r.steps) ? r.steps : []).filter((s): s is string => typeof s === "string"),
    });
  }
  return out;
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

/** Form fields for a use case's options. A null default is an optional number (as in the server's config). */
export function paramFields(uc: UseCase): ParamField[] {
  return Object.entries(uc.params).map(([key, def]) => {
    const hit = UNIT_SUFFIX.find(([suffix]) => key.endsWith(suffix));
    return {
      key,
      label: humanise(hit ? key.slice(0, -hit[0].length) : key),
      unit: hit?.[1] ?? "",
      numeric: def === null || typeof def === "number",
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
