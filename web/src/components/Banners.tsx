import { Sparkles } from "lucide-react";
import { isDirectMode, isSampleMode } from "@/api/client";
import { shortId } from "@/lib/format";
import { useSession } from "@/lib/runlog";
import { useServiceStatus } from "@/lib/serviceStatus";
import { texts, tr } from "@/lib/i18n";
import type { Experience } from "@/lib/tiers";

const T = texts({
  en: {
    prototype: "Open-source prototype · not an official service",
    disclosure: {
      public: "Answers are prepared with AI assistance from open data. They are for information only and are not official notices.",
      staff: "Answers and reports are prepared with AI assistance from open and simulated data. They support decisions by Roma Capitale officers; they do not make them.",
    } as Record<Experience, string>,
    sample: "Sample data",
    sampleDetail: "The tool API is not connected, so every value on screen is a placeholder. Labels show the kind each layer will have.",
    sampleBanner: "SAMPLE DATA",
    direct: "Live service · public data",
    directDetail: "Live data from the public tool API, without the secure staff gateway: office-only details are not served.",
    live: "Live service",
    liveDetail: "Live data through the secure office gateway.",
    waking: "Live service · waking up",
    wakingBanner: "The live service is waking up after a pause. The first answer can take two to three minutes; this screen keeps trying by itself.",
    signedInAs: "Signed in as",
    staff: "city staff",
    resident: "resident",
    runs: "Tool runs this session",
    lastRun: "Last run",
    promise: "Every figure carries a run id and a real / estimated / simulated label.",
  },
  it: {
    prototype: "Prototipo open source · non è un servizio ufficiale",
    disclosure: {
      public: "Le risposte sono preparate con l'aiuto dell'AI a partire da dati aperti. Sono solo informative e non sono avvisi ufficiali.",
      staff: "Risposte e relazioni sono preparate con l'aiuto dell'AI a partire da dati aperti e simulati. Aiutano il personale di Roma Capitale a decidere; non decidono al suo posto.",
    } as Record<Experience, string>,
    sample: "Dati di esempio",
    sampleDetail: "Il servizio dati non è collegato: ogni valore a schermo è un segnaposto. Le etichette mostrano il tipo che avrà ogni livello.",
    sampleBanner: "DATI DI ESEMPIO",
    direct: "Servizio live · dati pubblici",
    directDetail: "Dati live dal servizio pubblico, senza l'accesso protetto del personale: i dettagli riservati agli uffici non vengono forniti.",
    live: "Servizio live",
    liveDetail: "Dati live attraverso l'accesso protetto degli uffici.",
    waking: "Servizio live · in avvio",
    wakingBanner: "Il servizio live si sta riavviando dopo una pausa. La prima risposta può richiedere due o tre minuti; questa schermata riprova da sola.",
    signedInAs: "Accesso come",
    staff: "personale del Comune",
    resident: "cittadino",
    runs: "Esecuzioni in questa sessione",
    lastRun: "Ultima esecuzione",
    promise: "Ogni numero ha un id esecuzione e un'etichetta reale / stimato / simulato.",
  },
});

/** Always on screen: who made this and that AI is involved. */
export function AiDisclosure({ audience }: { audience: Experience }) {
  const t = tr(T);
  return (
    <div className="flex items-center gap-3 bg-chrome-deep px-4 py-1 text-2xs text-chrome-muted">
      <span className="hidden shrink-0 font-semibold uppercase tracking-[0.08em] md:inline">{t.prototype}</span>
      <span className="flex min-w-0 flex-1 items-center justify-end gap-1.5 text-right">
        <Sparkles className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="truncate" title={t.disclosure[audience]}>
          {t.disclosure[audience]}
        </span>
      </span>
    </div>
  );
}

/** Where the numbers on screen come from right now. */
export function connectionState(): { label: string; detail: string; tone: "live" | "sample" } {
  const t = tr(T);
  if (isSampleMode) return { label: t.sample, detail: t.sampleDetail, tone: "sample" };
  if (isDirectMode) return { label: t.direct, detail: t.directDetail, tone: "live" };
  return { label: t.live, detail: t.liveDetail, tone: "live" };
}

/** Full-width warning, only when the app is showing placeholder data. */
export function SampleModeBanner() {
  if (!isSampleMode) return null;
  return (
    <div role="status" className="border-b border-estimated/40 bg-estimated/15 px-4 py-1 text-center text-xs font-semibold text-estimated">
      {tr(T).sampleBanner} · {connectionState().detail}
    </div>
  );
}

/** Shown while the live service wakes up after a pause, so a slow first answer does not look like a failure. */
export function WakingBanner() {
  const waking = useServiceStatus() === "waking";
  if (isSampleMode || !waking) return null;
  return (
    <div role="status" className="animate-fade-in border-b border-primary/30 bg-primary-soft px-4 py-1 text-center text-xs font-semibold text-link">
      {tr(T).wakingBanner}
    </div>
  );
}

/** Bottom strip: connection, role, number of tool runs and the latest run id (the audit trail at a glance). */
export function StatusBar() {
  const { tier, runs } = useSession();
  const t = tr(T);
  const waking = useServiceStatus() === "waking";
  const base = connectionState();
  const c = waking && base.tone === "live" ? { ...base, label: t.waking } : base;
  const last = runs[0];
  return (
    <footer className="flex items-center gap-4 border-t border-line bg-surface px-4 py-1 text-2xs text-muted">
      <span className="flex items-center gap-1.5" title={c.detail}>
        <span className="relative flex h-2 w-2">
          {c.tone === "live" && <span className={`absolute inset-0 animate-pulse-ring rounded-full ${waking ? "bg-estimated" : "bg-real"}`} />}
          <span className={`relative h-2 w-2 rounded-full ${c.tone === "live" && !waking ? "bg-real" : "bg-estimated"}`} />
        </span>
        <span className="font-semibold text-ink">{c.label}</span>
      </span>
      <span>
        {t.signedInAs} <span className="font-semibold text-ink">{tier === "office" ? t.staff : t.resident}</span>
      </span>
      <span>
        {t.runs} <span className="num font-medium text-ink">{runs.length}</span>
      </span>
      {last && (
        <span className="hidden min-w-0 truncate sm:inline" title={last.env.run_id}>
          {t.lastRun} <code className="text-ink">{last.env.tool}</code> · <code>{shortId(last.env.run_id)}</code>
        </span>
      )}
      <span className="ml-auto hidden lg:inline">{t.promise}</span>
    </footer>
  );
}
