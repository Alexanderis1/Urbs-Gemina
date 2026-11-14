// How fresh the data on screen is: the saved copy with its time while the live data loads, then the LIVE badge.
// The badge is about freshness only; whether the data is real, estimated or simulated is the kind badge's job.
import { Clock } from "lucide-react";
import { Spinner } from "@/components/ui";
import { locale, texts, tr } from "@/lib/i18n";
import type { LiveState } from "@/lib/liveLayer";

const T = texts({
  en: {
    live: "Live",
    liveHint: "Just updated from the service. The badge goes when the data gets old, and the layer is asked again.",
    updated: (time: string) => `Updated at ${time}`,
    dataOf: (time: string) => `Data from ${time}`,
    loading: "Loading live data…",
    failed: "Update failed: trying again shortly.",
  },
  it: {
    live: "Live",
    liveHint: "Appena aggiornati dal servizio. Il bollino sparisce quando i dati invecchiano e il livello viene richiesto di nuovo.",
    updated: (time: string) => `Aggiornato alle ${time}`,
    dataOf: (time: string, today: boolean) => (today ? `Dati delle ${time}` : `Dati del ${time}`),
    loading: "Caricamento dati live…",
    failed: "Aggiornamento non riuscito: riprovo tra poco.",
  },
});

/** "10:42" for today, "13 nov, 10:42" for another day. */
function clock(at: number): { text: string; today: boolean } {
  const d = new Date(at);
  const today = d.toDateString() === new Date().toDateString();
  const text = today
    ? d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return { text, today };
}

export function LiveBadge({ live, className = "" }: { live: Pick<LiveState<unknown>, "phase" | "at">; className?: string }) {
  const t = tr(T);
  if (live.at === null || live.phase === "loading" || live.phase === "error") return null;
  const { text, today } = clock(live.at);
  if (live.phase === "live") {
    return (
      <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted animate-fade-in ${className}`}>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-real px-2 py-0.5 text-2xs font-bold uppercase tracking-[0.08em] text-surface" title={t.liveHint}>
          <span className="relative flex h-1.5 w-1.5" aria-hidden="true">
            <span className="absolute inset-0 rounded-full bg-surface motion-safe:animate-pulse-ring" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-surface" />
          </span>
          {t.live}
        </span>
        <span className="tabular-nums">{t.updated(text)}</span>
      </div>
    );
  }
  return (
    <div className={`flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs ${className}`}>
      <span className="inline-flex items-center gap-1 font-semibold tabular-nums text-ink">
        <Clock className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
        {t.dataOf(text, today)}
      </span>
      {live.phase === "refreshing" ? (
        <span className="inline-flex items-center gap-1.5 text-muted">
          <Spinner className="h-3.5 w-3.5" />
          {t.loading}
        </span>
      ) : (
        <span className="text-estimated">{t.failed}</span>
      )}
    </div>
  );
}
