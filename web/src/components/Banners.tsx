import { Sparkles } from "lucide-react";
import { isDirectMode, isSampleMode } from "@/api/client";
import { shortId } from "@/lib/format";
import { useSession } from "@/lib/runlog";
import { useServiceStatus } from "@/lib/serviceStatus";
import type { Experience } from "@/lib/tiers";

const DISCLOSURE: Record<Experience, string> = {
  public: "Answers are prepared with AI assistance from open data. They are for information only and are not official notices.",
  staff: "Answers and reports are prepared with AI assistance from open and simulated data. They support decisions by Roma Capitale officers; they do not make them.",
};

/** Always on screen: who made this and that AI is involved. */
export function AiDisclosure({ audience }: { audience: Experience }) {
  return (
    <div className="flex items-center gap-3 bg-chrome-deep px-4 py-1 text-2xs text-chrome-muted">
      <span className="hidden shrink-0 font-semibold uppercase tracking-[0.08em] md:inline">Open-source prototype · not an official service</span>
      <span className="flex min-w-0 flex-1 items-center justify-end gap-1.5 text-right">
        <Sparkles className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="truncate" title={DISCLOSURE[audience]}>
          {DISCLOSURE[audience]}
        </span>
      </span>
    </div>
  );
}

/** Where the numbers on screen come from right now. */
export function connectionState(): { label: string; detail: string; tone: "live" | "sample" } {
  if (isSampleMode)
    return {
      label: "Sample data",
      detail: "The tool API is not connected, so every value on screen is a placeholder. Labels show the kind each layer will have.",
      tone: "sample",
    };
  if (isDirectMode)
    return { label: "Live service · public data", detail: "Live data from the public tool API, without the secure staff gateway: office-only details are not served.", tone: "live" };
  return { label: "Live service", detail: "Live data through the secure office gateway.", tone: "live" };
}

/** Full-width warning, only when the app is showing placeholder data. */
export function SampleModeBanner() {
  if (!isSampleMode) return null;
  return (
    <div role="status" className="border-b border-estimated/40 bg-estimated/15 px-4 py-1 text-center text-xs font-semibold text-estimated">
      SAMPLE DATA · {connectionState().detail}
    </div>
  );
}

/** Shown while the live service wakes up after a pause, so a slow first answer does not look like a failure. */
export function WakingBanner() {
  const waking = useServiceStatus() === "waking";
  if (isSampleMode || !waking) return null;
  return (
    <div role="status" className="animate-fade-in border-b border-primary/30 bg-primary-soft px-4 py-1 text-center text-xs font-semibold text-link">
      The live service is waking up after a pause. The first answer can take two to three minutes; this screen keeps trying by itself.
    </div>
  );
}

/** Bottom strip: connection, tier, number of tool runs and the latest run id (the audit trail at a glance). */
export function StatusBar() {
  const { tier, runs } = useSession();
  const waking = useServiceStatus() === "waking";
  const base = connectionState();
  const c = waking && base.tone === "live" ? { ...base, label: "Live service · waking up" } : base;
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
        Signed in as <span className="font-semibold text-ink">{tier === "office" ? "city staff" : "resident"}</span>
      </span>
      <span>
        Tool runs this session <span className="num font-medium text-ink">{runs.length}</span>
      </span>
      {last && (
        <span className="hidden min-w-0 truncate sm:inline" title={last.env.run_id}>
          Last run <code className="text-ink">{last.env.tool}</code> · <code>{shortId(last.env.run_id)}</code>
        </span>
      )}
      <span className="ml-auto hidden lg:inline">Every figure carries a run id and a real / estimated / simulated label.</span>
    </footer>
  );
}
