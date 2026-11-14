import type { DataKind } from "@/api/types";
import { KIND_META, type KindKey } from "@/lib/theme";

const STYLE: Record<KindKey, string> = {
  real: "border-real/45 bg-real/10 text-real",
  estimated: "border-estimated/45 bg-estimated/10 text-estimated",
  simulated: "border-simulated/50 bg-simulated/10 text-simulated",
  what_if: "border-whatif/50 bg-whatif/10 text-whatif border-dashed",
  not_available: "border-line-strong bg-sunken text-muted",
};

/** Shape per kind, so the label does not depend on colour alone. */
export function KindGlyph({ kind, className = "h-2.5 w-2.5" }: { kind: KindKey; className?: string }) {
  const g = KIND_META[kind].glyph;
  return (
    <svg viewBox="0 0 10 10" className={`shrink-0 ${className}`} aria-hidden="true">
      {g === "solid" && <circle cx="5" cy="5" r="4" fill="currentColor" />}
      {g === "half" && (
        <>
          <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <path d="M5 1.4a3.6 3.6 0 0 0 0 7.2z" fill="currentColor" />
        </>
      )}
      {g === "dashed" && <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2 1.6" />}
      {g === "diamond" && <path d="M5 0.8 9.2 5 5 9.2 0.8 5z" fill="none" stroke="currentColor" strokeWidth="1.3" />}
      {g === "empty" && (
        <>
          <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <path d="M2.4 7.6 7.6 2.4" stroke="currentColor" strokeWidth="1.2" />
        </>
      )}
    </svg>
  );
}

/**
 * The data-honesty label. `text="what-if"` (or a `what_if` layer) switches to the what-if style.
 * `label` prefixes the layer name; `text` overrides the wording (e.g. "3 real").
 */
export function KindBadge({ kind, label, text, size = "sm" }: { kind: DataKind; label?: string; text?: string; size?: "sm" | "md" }) {
  const key: KindKey = kind === "hypothetical" || text === "what-if" || label === "what-if" || label === "what_if" ? "what_if" : kind;
  const meta = KIND_META[key];
  const shown = text ?? (key === "what_if" ? "what-if" : meta.label);
  const prefix = label && label !== "what_if" && label !== "what-if" ? label.replace(/_/g, " ") : "";
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm border font-bold uppercase tracking-[0.06em] ${
        size === "md" ? "px-2 py-1 text-xs" : "px-1.5 py-0.5 text-2xs"
      } ${STYLE[key]}`}
      title={meta.hint}
    >
      <KindGlyph kind={key} />
      {prefix && <span className="font-semibold normal-case tracking-normal opacity-80">{prefix}</span>}
      {shown}
    </span>
  );
}

/** Marks placeholder values while the tool API is not connected. Independent of the data kind. */
export function SampleBadge() {
  return (
    <span
      className="inline-flex items-center rounded-sm border border-estimated/50 bg-estimated/15 px-1.5 py-0.5 text-2xs font-bold uppercase tracking-[0.06em] text-estimated"
      title="Placeholder value: the tool API is not connected"
    >
      sample data
    </span>
  );
}
