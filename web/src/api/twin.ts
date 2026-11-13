// Orchestrator hand-over (shared interface 7), browser side.
// The tier is NOT sent: the edge function sets it from the Supabase session.
import { DATA_KINDS, type DataKind } from "./types";
import { parseMapActions, type MapAction } from "@/lib/mapActions";

export type Language = "it" | "en";

export interface TwinQuestionBody {
  question: string;
  language: Language;
  area: string | null;
  mode: "question" | "briefing";
  conversation_id: string | null;
}

export interface TwinAnswer {
  text: string;
  verified: boolean;
  run_ids: string[];
  sources: string[];
  data_kinds: Record<string, DataKind>;
  synthetic: boolean;
  missing: string[];
  map_actions: MapAction[];
}

export function buildTwinQuestion(
  question: string,
  opts: { language: Language; area?: string | null; conversationId?: string | null; mode?: "question" | "briefing" },
): TwinQuestionBody {
  return {
    question,
    language: opts.language,
    area: opts.area ?? null,
    mode: opts.mode ?? "question",
    conversation_id: opts.conversationId ?? null,
  };
}

const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);

/** Mirrors voice/contract.py answer_from_json: unknown or missing fields fail safe. */
export function parseTwinAnswer(raw: unknown): TwinAnswer {
  const d = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  const kinds: Record<string, DataKind> = {};
  if (typeof d.data_kinds === "object" && d.data_kinds !== null) {
    for (const [k, v] of Object.entries(d.data_kinds)) if (DATA_KINDS.includes(v as DataKind)) kinds[k] = v as DataKind;
  }
  return {
    text: String(d.text ?? ""),
    verified: d.verified === true,
    run_ids: strs(d.run_ids),
    sources: strs(d.sources),
    data_kinds: kinds,
    synthetic: d.synthetic !== false,
    missing: strs(d.missing),
    map_actions: parseMapActions(d.map_actions),
  };
}
