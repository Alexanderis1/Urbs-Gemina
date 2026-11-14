// Orchestrator hand-over (shared interface 7, agents/contract.py), browser side.
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
  /** Tool trace from WS7: one entry per citation tag in the text. Empty when the orchestrator sends none. */
  citations: Citation[];
}

/** Citation tag kinds, as in agents/verifier.py CITATION: [run:...], [src:...], [data:...]. */
export const CITATION_KINDS = ["run", "src", "data"] as const;
export type CitationKind = (typeof CITATION_KINDS)[number];

export interface Citation {
  /** 0-based index of the line in answer.text split on newlines. */
  line: number;
  kind: CitationKind;
  ref: string;
  /** "auto" means code attached it after checking every figure on the line against one tool run. */
  cite_mode: "explicit" | "auto";
}

function parseCitations(v: unknown): Citation[] {
  if (!Array.isArray(v)) return [];
  const out: Citation[] = [];
  for (const c of v) {
    if (typeof c !== "object" || c === null) continue;
    const r = c as Record<string, unknown>;
    if (typeof r.line !== "number" || !Number.isInteger(r.line) || r.line < 0) continue;
    if (!CITATION_KINDS.includes(r.kind as CitationKind) || typeof r.ref !== "string" || !r.ref) continue;
    out.push({ line: r.line, kind: r.kind as CitationKind, ref: r.ref, cite_mode: r.cite_mode === "auto" ? "auto" : "explicit" });
  }
  return out;
}

const TAG = /\s*\[(run|src|data):[^\]\s]+\]/g;

/** Answer lines that carry citations, with the tags removed from the shown text. */
export function citationRows(a: TwinAnswer): { line: number; text: string; citations: Citation[] }[] {
  const lines = a.text.split("\n");
  const byLine = new Map<number, Citation[]>();
  for (const c of a.citations) byLine.set(c.line, [...(byLine.get(c.line) ?? []), c]);
  return [...byLine.entries()]
    .sort(([x], [y]) => x - y)
    .map(([line, citations]) => ({ line, text: (lines[line] ?? "").replace(TAG, "").trim(), citations }));
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
    citations: parseCitations(d.citations),
  };
}
