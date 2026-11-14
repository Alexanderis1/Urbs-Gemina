import { useEffect, useRef, useState } from "react";
import { Circle, Layers, MapPin, MessagesSquare, PanelsTopLeft, Send, ShieldAlert, ShieldCheck, Sparkles, Square, type LucideIcon } from "lucide-react";
import { isSampleMode, proxyFetch } from "@/api/client";
import { buildTwinQuestion, citationRows, parseTwinAnswer, type Citation, type Language, type TwinAnswer } from "@/api/twin";
import { KindBadge } from "@/components/Badge";
import { Callout, Segmented, Skeleton } from "@/components/ui";
import { dispatchMapAction } from "@/lib/mapbus";
import { shortId } from "@/lib/format";
import { parseAnswerText, type Inline } from "@/lib/answerText";
import { useSession } from "@/lib/runlog";
import type { ResolvePlaceResult } from "@/api/types";

interface Turn {
  role: "user" | "assistant" | "error";
  text: string;
  answer?: TwinAnswer;
}

// Orchestrator hand-over (shared interface 7) through the edge function's /ask route,
// which sets the tier from the session and forwards to ORCHESTRATOR_URL.

const OPENING: Turn = {
  role: "assistant",
  text: "I am an AI assistant for Roma Capitale. I answer from tool runs and cited sources, and I support decisions rather than make them.",
};

const ACTION_ICON: Record<string, LucideIcon> = {
  fly_to: MapPin,
  show_layer: Layers,
  show_radius: Circle,
  show_area: Square,
  open_screen: PanelsTopLeft,
};

const SUGGESTIONS = [
  "What is within 300 m of Via Nazionale 194?",
  "How is the air quality in Municipio I right now?",
  "Which hospitals are in Municipio II?",
  "Where are the sport deserts for football?",
];

const CODE_CHIP = "rounded-sm border border-line bg-sunken px-1";

const ACTION_LABEL: Record<string, string> = {
  fly_to: "Go to place",
  show_area: "Show area",
  show_layer: "Show layer",
  show_radius: "Show 300 m circle",
  open_screen: "Open screen",
};

export default function Ask() {
  const { run } = useSession();
  const [turns, setTurns] = useState<Turn[]>([OPENING]);
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [busy, setBusy] = useState(false);
  const conversationId = useRef(crypto.randomUUID());
  const endRef = useRef<HTMLDivElement>(null);

  const lastQuestionRef = useRef<HTMLDivElement>(null);

  // While waiting, keep the placeholder in view. When the answer arrives, put the question at the top
  // so the officer reads the answer from its first line (answers can be long).
  useEffect(() => {
    if (busy) endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    else lastQuestionRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [turns, busy]);
  const lastQuestion = turns.reduce((last, t, i) => (t.role === "user" ? i : last), -1);

  async function sampleAnswer(q: string): Promise<TwinAnswer> {
    // No language model in sample mode. One real tool call (to the sample tools) shows the trace format.
    const place = await run<ResolvePlaceResult>("resolve_place", { text: q });
    return parseTwinAnswer({
      text: `The assistant is not connected yet, so this is not an answer. It shows how answers will look: sources, run ids, data kinds and map buttons.\nSample place found [run:${place.run_id.slice(0, 12)}]`,
      verified: false,
      run_ids: [place.run_id],
      sources: place.sources.map((s) => s.id),
      data_kinds: place.data_kinds,
      synthetic: true,
      missing: ["orchestrator (agents workstream)"],
      citations: [{ line: 1, kind: "run", ref: place.run_id, cite_mode: "auto" }],
      map_actions: [
        { tool: "fly_to", args: { lon: place.result.lon, lat: place.result.lat, zoom: 15, label: place.result.label ?? q } },
        { tool: "show_layer", args: { layer: "air_quality", visible: true } },
      ],
    });
  }

  async function send(question?: string) {
    const q = (question ?? text).trim();
    if (busy) return;
    if (!q) return;
    setText("");
    setTurns((t) => [...t, { role: "user", text: q }]);
    setBusy(true);
    try {
      let answer: TwinAnswer;
      if (!isSampleMode) {
        const res = await proxyFetch("/ask", buildTwinQuestion(q, { language, conversationId: conversationId.current }));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        answer = parseTwinAnswer(await res.json());
      } else {
        answer = await sampleAnswer(q);
      }
      setTurns((t) => [...t, { role: "assistant", text: answer.text, answer }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "error", text: `The assistant could not answer: ${String(e)}` }]);
    } finally {
      setBusy(false);
    }
  }

  const onlyOpening = turns.length === 1;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          <header className="space-y-1">
            <h1 className="flex items-center gap-2 text-xl font-bold">
              <MessagesSquare className="h-5 w-5 text-link" aria-hidden="true" />
              Ask the twin
            </h1>
            <p className="hint">Answers come from tool runs and cited sources. Check the trace under each answer.</p>
          </header>
          <div className="space-y-3" aria-live="polite">
            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} ref={i === lastQuestion ? lastQuestionRef : undefined} className="flex animate-rise-in scroll-mt-4 justify-end">
                  <p className="max-w-[80%] whitespace-pre-wrap rounded bg-primary-soft px-3 py-2 text-sm leading-relaxed">{t.text}</p>
                </div>
              ) : t.role === "error" ? (
                <Callout key={i} tone="error" title="No answer">
                  {t.text}
                </Callout>
              ) : (
                <article key={i} className="card animate-rise-in space-y-3">
                  <div className="label flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                    AI assistant
                  </div>
                  <AnswerText text={t.text} />
                  {t.answer && <AnswerTrace a={t.answer} />}
                </article>
              ),
            )}
            {busy && (
              <div className="card animate-rise-in space-y-3">
                <div className="label flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  AI assistant
                </div>
                <Skeleton lines={3} />
                <p className="hint">Running tools and checking figures…</p>
              </div>
            )}
          </div>
          {onlyOpening && !busy && (
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="btn-ghost btn-sm"
                  onClick={() => {
                    setText(q);
                    void send(q);
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>
      <div className="border-t border-line bg-surface">
        <form
          className="mx-auto flex max-w-3xl flex-wrap items-center gap-2 px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="w-28 shrink-0">
            <Segmented
              label="Answer language"
              value={language}
              onChange={setLanguage}
              options={[
                { id: "en", label: "EN" },
                { id: "it", label: "IT" },
              ]}
            />
          </div>
          <input
            className="input min-w-0 flex-1"
            aria-label="Your question"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask about a place, a layer or a scenario…"
          />
          <button type="submit" className="btn" disabled={busy || !text.trim()}>
            <Send className="h-4 w-4" aria-hidden="true" />
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}

function AnswerTrace({ a }: { a: TwinAnswer }) {
  const rows = citationRows(a);
  return (
    <div className="space-y-3 border-t border-line pt-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${a.verified ? "text-real" : "text-estimated"}`}>
          {a.verified ? <ShieldCheck className="h-4 w-4" aria-hidden="true" /> : <ShieldAlert className="h-4 w-4" aria-hidden="true" />}
          {a.verified ? "Every figure traced to a run or source" : "Not verified: treat as a draft"}
        </span>
        {a.synthetic && <KindBadge kind="simulated" />}
        {(["real", "estimated", "simulated", "not_available"] as const).map((k) => {
          const n = Object.values(a.data_kinds).filter((x) => x === k).length;
          return n ? <KindBadge key={k} kind={k} text={`${n} ${k.replace("_", " ")}`} /> : null;
        })}
      </div>
      {a.missing.length > 0 && (
        <Callout tone="warn" title="Missing">
          {a.missing.join(", ")}
        </Callout>
      )}
      {a.map_actions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {a.map_actions.map((m, i) => {
            const Icon = ACTION_ICON[m.tool];
            return (
              <button key={i} type="button" className="btn-ghost btn-sm" onClick={() => dispatchMapAction(m)}>
                {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
                {ACTION_LABEL[m.tool]}
                {m.tool === "fly_to" && m.args.label ? `: ${m.args.label}` : ""}
                {m.tool === "show_layer" ? `: ${m.args.layer}` : ""}
              </button>
            );
          })}
          <button type="button" className="btn btn-sm" onClick={() => a.map_actions.forEach((m) => dispatchMapAction(m))}>
            Show all on map
          </button>
        </div>
      )}
      <div className="space-y-2">
        {a.citations.length > 0 && (
          <details>
            <summary className="label cursor-pointer">Citations per line ({a.citations.length})</summary>
            <ul className="mt-2 space-y-1.5">
              {rows.map((row) => (
                <li key={row.line} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="italic text-muted">“{row.text.replace(/\*\*/g, "").replace(/^[-*•]\s+/, "") || `line ${row.line + 1}`}”</span>
                  {row.citations.map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1">
                      <CitationRef c={c} />
                      {c.cite_mode === "auto" && (
                        <span
                          className="rounded-sm border border-line-strong px-1 text-2xs text-muted"
                          title="Attached by code: every figure on this line matches this tool run."
                        >
                          auto
                        </span>
                      )}
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </details>
        )}
        {Object.keys(a.data_kinds).length > 0 && (
          <details>
            <summary className="label cursor-pointer">Layers used</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(a.data_kinds).map(([l, k]) => (
                <KindBadge key={l} kind={k} label={l} />
              ))}
            </div>
          </details>
        )}
        {a.run_ids.length > 0 && (
          <details>
            <summary className="label cursor-pointer">Runs ({a.run_ids.length})</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {a.run_ids.map((r) => (
                <code key={r} className={CODE_CHIP} title={r}>
                  {shortId(r)}
                </code>
              ))}
            </div>
          </details>
        )}
        {a.sources.length > 0 && (
          <details>
            <summary className="label cursor-pointer">Sources ({a.sources.length})</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {a.sources.map((s) => (
                <code key={s} className={`${CODE_CHIP} break-all`}>
                  {s}
                </code>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

function CitationRef({ c }: { c: Citation }) {
  if (c.kind === "src" && /^https?:\/\//.test(c.ref))
    return (
      <a className="text-link underline" href={c.ref} target="_blank" rel="noreferrer">
        source
      </a>
    );
  const label = c.kind === "run" ? `run ${shortId(c.ref)}` : `${c.kind === "src" ? "source" : "data"} ${c.ref}`;
  return (
    <code className={CODE_CHIP} title={c.ref}>
      {label}
    </code>
  );
}

/** The answer body: light Markdown from the assistant, with each citation as a small chip next to its sentence. */
function AnswerText({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {parseAnswerText(text).map((b, i) =>
        b.type === "heading" ? (
          <h3 key={i} className="pt-1 text-sm font-bold">
            {b.text}
          </h3>
        ) : b.type === "list" ? (
          <ul key={i} className="ml-1 space-y-1 border-l-2 border-line pl-3">
            {b.items.map((item, j) => (
              <li key={j}>
                <InlineText parts={item} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <InlineText parts={b.inline} />
          </p>
        ),
      )}
    </div>
  );
}

function InlineText({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.type === "text" ? (
          <span key={i}>{p.text}</span>
        ) : p.type === "bold" ? (
          <strong key={i} className="font-bold">
            {p.text}
          </strong>
        ) : p.kind === "src" && /^https?:\/\//.test(p.ref) ? (
          <a key={i} className="mx-0.5 whitespace-nowrap text-xs hover:underline" href={p.ref} target="_blank" rel="noreferrer">
            source
          </a>
        ) : (
          <code
            key={i}
            className="mx-0.5 whitespace-nowrap rounded-sm border border-line bg-sunken px-1 align-baseline text-2xs text-muted"
            title={`${p.kind === "run" ? "Tool run" : p.kind === "src" ? "Source" : "Data"} ${p.ref}`}
          >
            {p.kind === "run" ? `run ${shortId(p.ref).slice(0, 6)}` : p.ref}
          </code>
        ),
      )}
    </>
  );
}
