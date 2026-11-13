import type { DataKind } from "@/api/types";

const STYLE: Record<DataKind, string> = {
  real: "bg-real/10 text-real border-real/40",
  estimated: "bg-estimated/10 text-estimated border-estimated/40",
  simulated: "bg-simulated/10 text-simulated border-simulated/50",
  not_available: "bg-stone-100 text-stone-500 border-stone-300",
};

export function KindBadge({ kind, label, text }: { kind: DataKind; label?: string; text?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${STYLE[kind]}`}
      title={
        text === "what-if"
          ? "A hypothetical change entered by the user, not existing data"
          : kind === "simulated"
            ? "Simulated traffic loop data, not a measurement"
            : kind === "estimated"
              ? "Modelled or crowd-sourced estimate, with a range"
              : undefined
      }
    >
      {label ? `${label}: ` : ""}
      {text ?? kind.replace("_", " ")}
    </span>
  );
}

/** Marks placeholder values while the tool API is not connected. Independent of the data kind. */
export function SampleBadge() {
  return (
    <span
      className="inline-flex items-center rounded border border-amber-400 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700"
      title="Placeholder value: the tool API is not connected"
    >
      sample data
    </span>
  );
}
