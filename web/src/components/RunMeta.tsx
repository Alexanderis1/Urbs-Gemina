import { AlertTriangle, ExternalLink } from "lucide-react";
import { badgeText, envelopeBadge, layerBadges, extraWarnings } from "@/api/envelope";
import { isSampleMode } from "@/api/client";
import type { Envelope } from "@/api/types";
import { shortId } from "@/lib/format";
import { texts, tr } from "@/lib/i18n";
import { KindBadge, SampleBadge } from "./Badge";
import { Callout } from "./ui";

const T = texts({
  en: {
    runId: "Run id",
    run: "run",
    cached: "cached",
    refused: "Refused by a safeguard",
    notAvailable: "Not available",
    layerKinds: "Kind of each layer used",
    sources: "Sources",
    retrieved: "retrieved",
  },
  it: {
    runId: "Id esecuzione",
    run: "esecuzione",
    cached: "in cache",
    refused: "Rifiutato da una protezione",
    notAvailable: "Non disponibile",
    layerKinds: "Tipo di dato di ogni livello usato",
    sources: "Fonti",
    retrieved: "recuperato il",
  },
});

/** Tool trace for one run: overall label, run id, the kind of every layer used, sources and warnings. */
export function RunMeta({ env, compact = false }: { env: Envelope; compact?: boolean }) {
  const t = tr(T);
  const layers = layerBadges(env);
  return (
    <div className="space-y-2 text-xs text-muted">
      <div className="flex flex-wrap items-center gap-1.5">
        <KindBadge kind={envelopeBadge(env)} text={badgeText(env)} />
        {isSampleMode && <SampleBadge />}
        <code className="rounded-sm border border-line bg-sunken px-1.5 py-0.5 text-2xs" title={`${t.runId} ${env.run_id}`}>
          {env.tool} · {t.run} {shortId(env.run_id)}
        </code>
        {env.cached && <span className="rounded-sm border border-line px-1 text-2xs">{t.cached}</span>}
      </div>
      {env.status && env.status !== "ok" && (
        <Callout tone={env.status === "refused" ? "warn" : "error"} title={env.status === "refused" ? t.refused : t.notAvailable}>
          {env.reason}
        </Callout>
      )}
      {!compact && layers.length > 0 && (
        <div className="flex flex-wrap gap-1" aria-label={t.layerKinds}>
          {layers.map(([l, k]) => (
            <KindBadge key={l} kind={k} label={l} text={l === "what_if" ? "what-if" : undefined} />
          ))}
        </div>
      )}
      {!compact && env.sources.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer select-none font-semibold hover:text-ink">{t.sources} ({env.sources.length})</summary>
          <ul className="mt-1 space-y-0.5 border-l-2 border-line pl-2">
            {env.sources.map((s) => (
              <li key={s.id} className="break-words">
                {s.url ? (
                  <a className="inline-flex items-center gap-1 hover:underline" href={s.url} target="_blank" rel="noreferrer">
                    {s.id}
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                ) : (
                  <span className="text-ink">{s.id}</span>
                )}
                {s.retrieved_at ? ` · ${t.retrieved} ${s.retrieved_at}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {extraWarnings(env).map((w) => (
        <p key={w} className="flex gap-1.5 text-estimated">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span className="break-words">{w}</span>
        </p>
      ))}
    </div>
  );
}
