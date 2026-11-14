// How an answer of the assistant is shown, on every screen that asks the twin: the text with its citation
// chips, and the trace under it (what was checked, map buttons, citations, layers, runs, sources).
import { Circle, Layers, MapPin, PanelsTopLeft, ShieldAlert, ShieldCheck, Square, type LucideIcon } from "lucide-react";
import { citationRows, type Citation, type TwinAnswer } from "@/api/twin";
import { KindBadge } from "@/components/Badge";
import { Callout } from "@/components/ui";
import { dispatchMapAction } from "@/lib/mapbus";
import { shortId } from "@/lib/format";
import { texts, tr } from "@/lib/i18n";
import { KIND_META } from "@/lib/theme";
import { parseAnswerText, type Inline } from "@/lib/answerText";

const ACTION_ICON: Record<string, LucideIcon> = {
  fly_to: MapPin,
  show_layer: Layers,
  show_radius: Circle,
  show_area: Square,
  open_screen: PanelsTopLeft,
};

const CODE_CHIP = "rounded-sm border border-line bg-sunken px-1";

const T = texts({
  en: {
    actions: {
      fly_to: "Go to place",
      show_area: "Show area",
      show_layer: "Show layer",
      show_radius: "Show 300 m circle",
      open_screen: "Open screen",
    } as Record<string, string>,
    verified: "Every figure traced to a run or source",
    notVerified: "Not verified: treat as a draft",
    kindCount: (n: number, raw: string, _label: string) => `${n} ${raw}`,
    missing: "Missing",
    showAll: "Show all on map",
    citationsPerLine: (n: number) => `Citations per line (${n})`,
    line: (n: number) => `line ${n}`,
    autoTitle: "Attached by code: every figure on this line matches this tool run.",
    auto: "auto",
    layersUsed: "Layers used",
    runs: (n: number) => `Runs (${n})`,
    sources: (n: number) => `Sources (${n})`,
    source: "source",
    run: "run",
    data: "data",
    toolRun: "Tool run",
    sourceCap: "Source",
    dataCap: "Data",
  },
  it: {
    actions: {
      fly_to: "Vai al luogo",
      show_area: "Mostra l'area",
      show_layer: "Mostra il livello",
      show_radius: "Mostra il cerchio di 300 m",
      open_screen: "Apri la schermata",
    } as Record<string, string>,
    verified: "Ogni cifra è collegata a un'esecuzione o a una fonte",
    notVerified: "Non verificato: consideralo una bozza",
    kindCount: (n: number, _raw: string, label: string) => `${n} ${label}`,
    missing: "Mancante",
    showAll: "Mostra tutto sulla mappa",
    citationsPerLine: (n: number) => `Citazioni per riga (${n})`,
    line: (n: number) => `riga ${n}`,
    autoTitle: "Aggiunta dal codice: ogni cifra di questa riga corrisponde a questa esecuzione.",
    auto: "auto",
    layersUsed: "Livelli usati",
    runs: (n: number) => `Esecuzioni (${n})`,
    sources: (n: number) => `Fonti (${n})`,
    source: "fonte",
    run: "esecuzione",
    data: "dato",
    toolRun: "Esecuzione dello strumento",
    sourceCap: "Fonte",
    dataCap: "Dato",
  },
});

export function AnswerTrace({ a }: { a: TwinAnswer }) {
  const t = tr(T);
  const rows = citationRows(a);
  return (
    <div className="space-y-3 border-t border-line pt-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 text-sm font-semibold ${a.verified ? "text-real" : "text-estimated"}`}>
          {a.verified ? <ShieldCheck className="h-4 w-4" aria-hidden="true" /> : <ShieldAlert className="h-4 w-4" aria-hidden="true" />}
          {a.verified ? t.verified : t.notVerified}
        </span>
        {a.synthetic && <KindBadge kind="simulated" />}
        {(["real", "estimated", "simulated", "not_available"] as const).map((k) => {
          const n = Object.values(a.data_kinds).filter((x) => x === k).length;
          return n ? <KindBadge key={k} kind={k} text={t.kindCount(n, k.replace("_", " "), KIND_META[k].label.toLowerCase())} /> : null;
        })}
      </div>
      {a.missing.length > 0 && (
        <Callout tone="warn" title={t.missing}>
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
                {t.actions[m.tool]}
                {m.tool === "fly_to" && m.args.label ? `: ${m.args.label}` : ""}
                {m.tool === "show_layer" ? `: ${m.args.layer}` : ""}
              </button>
            );
          })}
          <button type="button" className="btn btn-sm" onClick={() => a.map_actions.forEach((m) => dispatchMapAction(m))}>
            {t.showAll}
          </button>
        </div>
      )}
      <div className="space-y-2">
        {a.citations.length > 0 && (
          <details>
            <summary className="label cursor-pointer">{t.citationsPerLine(a.citations.length)}</summary>
            <ul className="mt-2 space-y-1.5">
              {rows.map((row) => (
                <li key={row.line} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="italic text-muted">“{row.text.replace(/\*\*/g, "").replace(/^[-*•]\s+/, "") || t.line(row.line + 1)}”</span>
                  {row.citations.map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1">
                      <CitationRef c={c} />
                      {c.cite_mode === "auto" && (
                        <span
                          className="rounded-sm border border-line-strong px-1 text-2xs text-muted"
                          title={t.autoTitle}
                        >
                          {t.auto}
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
            <summary className="label cursor-pointer">{t.layersUsed}</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(a.data_kinds).map(([l, k]) => (
                <KindBadge key={l} kind={k} label={l} />
              ))}
            </div>
          </details>
        )}
        {a.run_ids.length > 0 && (
          <details>
            <summary className="label cursor-pointer">{t.runs(a.run_ids.length)}</summary>
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
            <summary className="label cursor-pointer">{t.sources(a.sources.length)}</summary>
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
  const t = tr(T);
  if (c.kind === "src" && /^https?:\/\//.test(c.ref))
    return (
      <a className="text-link underline" href={c.ref} target="_blank" rel="noreferrer">
        {t.source}
      </a>
    );
  const label = c.kind === "run" ? `${t.run} ${shortId(c.ref)}` : `${c.kind === "src" ? t.source : t.data} ${c.ref}`;
  return (
    <code className={CODE_CHIP} title={c.ref}>
      {label}
    </code>
  );
}

/**
 * The answer body: light Markdown from the assistant, with each citation as a small chip next to its sentence.
 * `plain` (public service) keeps links to sources and drops the run and data chips: they stay under "How we know this".
 */
export function AnswerText({ text, plain = false }: { text: string; plain?: boolean }) {
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
                <InlineText parts={item} plain={plain} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <InlineText parts={b.inline} plain={plain} />
          </p>
        ),
      )}
    </div>
  );
}

function InlineText({ parts, plain }: { parts: Inline[]; plain: boolean }) {
  const t = tr(T);
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
            {t.source}
          </a>
        ) : plain ? null : (
          <code
            key={i}
            className="mx-0.5 whitespace-nowrap rounded-sm border border-line bg-sunken px-1 align-baseline text-2xs text-muted"
            title={`${p.kind === "run" ? t.toolRun : p.kind === "src" ? t.sourceCap : t.dataCap} ${p.ref}`}
          >
            {p.kind === "run" ? `${t.run} ${shortId(p.ref).slice(0, 6)}` : p.ref}
          </code>
        ),
      )}
    </>
  );
}
