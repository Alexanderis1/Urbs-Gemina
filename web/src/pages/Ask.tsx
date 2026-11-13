import { useRef, useState } from "react";
import { PROXY, isSampleMode } from "@/api/client";
import { buildTwinQuestion, parseTwinAnswer, type Language, type TwinAnswer } from "@/api/twin";
import { KindBadge } from "@/components/Badge";
import { dispatchMapAction } from "@/lib/mapbus";
import { shortId } from "@/lib/format";
import { useSession } from "@/lib/runlog";
import type { ResolvePlaceResult } from "@/api/types";

interface Turn {
  role: "user" | "assistant";
  text: string;
  answer?: TwinAnswer;
}

// Orchestrator hand-over (shared interface 7) through the edge function, which adds the tier from the session.
// The "/ask" path on the proxy is provisional until WS7 fixes the route.
const ASK_URL = (import.meta.env.VITE_ASK_URL as string | undefined) || (PROXY ? `${PROXY}/ask` : "");

const OPENING: Turn = {
  role: "assistant",
  text: "I am an AI assistant for Roma Capitale. I answer from tool runs and cited sources, and I support decisions rather than make them.",
};

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

  async function sampleAnswer(q: string): Promise<TwinAnswer> {
    // No language model in sample mode. One real tool call (to the sample tools) shows the trace format.
    const place = await run<ResolvePlaceResult>("resolve_place", { text: q });
    return parseTwinAnswer({
      text: "The assistant is not connected yet, so this is not an answer. It shows how answers will look: sources, run ids, data kinds and map buttons.",
      verified: false,
      run_ids: [place.run_id],
      sources: place.sources.map((s) => s.id),
      data_kinds: place.data_kinds,
      synthetic: true,
      missing: ["orchestrator (agents workstream)"],
      map_actions: [
        { tool: "fly_to", args: { lon: place.result.lon, lat: place.result.lat, zoom: 15, label: place.result.label ?? q } },
        { tool: "show_layer", args: { layer: "air_quality", visible: true } },
      ],
    });
  }

  async function send() {
    const q = text.trim();
    if (!q) return;
    setText("");
    setTurns((t) => [...t, { role: "user", text: q }]);
    setBusy(true);
    try {
      let answer: TwinAnswer;
      if (ASK_URL && !isSampleMode) {
        const res = await fetch(ASK_URL, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(buildTwinQuestion(q, { language, conversationId: conversationId.current })),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        answer = parseTwinAnswer(await res.json());
      } else {
        answer = await sampleAnswer(q);
      }
      setTurns((t) => [...t, { role: "assistant", text: answer.text, answer }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "assistant", text: `Error: ${String(e)}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col p-4">
      <div className="flex-1 space-y-3 overflow-y-auto">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "ml-12 rounded-lg bg-roma/10 p-3" : "card mr-12 space-y-2"}>
            <p className="whitespace-pre-wrap text-sm">{t.text}</p>
            {t.answer && <AnswerTrace a={t.answer} />}
          </div>
        ))}
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <select className="rounded-md border border-stone-300 px-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value as Language)}>
          <option value="en">EN</option>
          <option value="it">IT</option>
        </select>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about a place, a layer or a scenario…" />
        <button className="btn" disabled={busy}>
          Ask
        </button>
      </form>
    </div>
  );
}

function AnswerTrace({ a }: { a: TwinAnswer }) {
  return (
    <div className="space-y-2 rounded bg-stone-50 p-2 text-xs text-stone-600">
      <div className="flex flex-wrap items-center gap-2">
        {a.synthetic && <KindBadge kind="simulated" />}
        <span className={a.verified ? "font-semibold text-real" : "font-semibold text-amber-700"}>
          {a.verified ? "✓ Every figure traced to a run or source" : "⚠ Not verified"}
        </span>
        {Object.entries(a.data_kinds).map(([l, k]) => (
          <KindBadge key={l} kind={k} label={l} />
        ))}
      </div>
      {a.run_ids.length > 0 && (
        <div>
          Runs:{" "}
          {a.run_ids.map((r) => (
            <code key={r} className="mr-1 rounded bg-white px-1" title={r}>
              {shortId(r)}
            </code>
          ))}
        </div>
      )}
      {a.sources.length > 0 && <div>Sources: {a.sources.join(", ")}</div>}
      {a.missing.length > 0 && <div className="text-amber-700">Missing: {a.missing.join(", ")}</div>}
      {a.map_actions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {a.map_actions.map((m, i) => (
            <button key={i} className="btn-ghost text-xs" onClick={() => dispatchMapAction(m)}>
              {ACTION_LABEL[m.tool]}
              {m.tool === "fly_to" && m.args.label ? `: ${m.args.label}` : ""}
              {m.tool === "show_layer" ? `: ${m.args.layer}` : ""}
            </button>
          ))}
          <button className="btn text-xs" onClick={() => a.map_actions.forEach((m) => dispatchMapAction(m))}>
            Show all on map
          </button>
        </div>
      )}
    </div>
  );
}
