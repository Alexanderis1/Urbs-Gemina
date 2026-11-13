import { envelopeBadge, layerBadges } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { shortId } from "@/lib/format";
import { KindBadge } from "./Badge";

/** Tool trace for one run: badge, run id, layer kinds, sources, warnings. */
export function RunMeta({ env, compact = false }: { env: Envelope; compact?: boolean }) {
  return (
    <div className="space-y-1 text-xs text-stone-600">
      <div className="flex flex-wrap items-center gap-2">
        <KindBadge kind={envelopeBadge(env)} />
        <code className="rounded bg-stone-100 px-1" title={env.run_id}>
          {env.tool} · run {shortId(env.run_id)}
        </code>
        {env.cached && <span className="text-stone-400">cached</span>}
        {!compact && layerBadges(env).map(([l, k]) => <KindBadge key={l} kind={k} label={l} />)}
      </div>
      {env.status && env.status !== "ok" && (
        <p className="font-medium text-red-700">
          {env.status === "refused" ? "Refused" : "Not available"}: {env.reason}
        </p>
      )}
      {!compact && (
        <ul className="list-inside list-disc">
          {env.sources.map((s) => (
            <li key={s.id}>
              {s.url ? (
                <a className="underline" href={s.url} target="_blank" rel="noreferrer">
                  {s.id}
                </a>
              ) : (
                s.id
              )}{" "}
              · retrieved {s.retrieved_at}
            </li>
          ))}
        </ul>
      )}
      {env.warnings.map((w) => (
        <p key={w} className="text-amber-700">
          ⚠ {w}
        </p>
      ))}
    </div>
  );
}
