import { envelopeBadge } from "@/api/envelope";
import type { Envelope } from "@/api/types";
import { texts, tr } from "@/lib/i18n";

// Client-side summary of the tool runs behind a permit check. The official cited report is built by
// the tool API (WS4); this file is the fallback download and never adds a number of its own.
export interface Application {
  operator?: string;
  height_m?: string;
  technology?: string;
  reference?: string;
}

const T = texts({
  en: {
    title: (address: string) => `Permit context check: ${address}`,
    application: "Application (as entered by the officer)",
    notGiven: "not given",
    operator: "Operator",
    height: "Antenna height above ground",
    technology: "Technology / bands",
    reference: "File reference",
    context: "Distances to sensitive sites are context, not a prohibition.",
    estimates: "Estimates are not measurements.",
    simulated: "> **SIMULATED**: this report uses simulated inputs (traffic loops or a what-if).",
    runId: "Run id",
    dataKinds: "Data kinds",
    sources: "Sources",
    retrieved: "retrieved",
    warnings: "Warnings",
  },
  it: {
    title: (address: string) => `Verifica del contesto dell'istanza: ${address}`,
    application: "Istanza (come inserita dall'operatore)",
    notGiven: "non indicato",
    operator: "Operatore",
    height: "Altezza dell'antenna da terra",
    technology: "Tecnologia / bande",
    reference: "Riferimento della pratica",
    context: "Le distanze dai siti sensibili sono un contesto, non un divieto.",
    estimates: "Le stime non sono misure.",
    simulated: "> **SIMULATO**: questa relazione usa dati simulati (spire del traffico o un'ipotesi).",
    runId: "Id esecuzione",
    dataKinds: "Tipi di dato",
    sources: "Fonti",
    retrieved: "acquisito",
    warnings: "Avvisi",
  },
});

export function buildCitedReport(address: string, runs: Envelope[], app: Application = {}): string {
  const t = tr(T);
  const lines: string[] = [
    `# ${t.title(address)}`,
    "",
    `## ${t.application}`,
    "",
    `- ${t.operator}: ${app.operator || t.notGiven}`,
    `- ${t.height}: ${app.height_m ? `${app.height_m} m` : t.notGiven}`,
    `- ${t.technology}: ${app.technology || t.notGiven}`,
    `- ${t.reference}: ${app.reference || t.notGiven}`,
    "",
    t.context,
    t.estimates,
    "",
  ];
  if (runs.some((r) => r.synthetic)) lines.push(t.simulated, "");
  for (const r of runs) {
    lines.push(`## ${r.tool} (${envelopeBadge(r).toUpperCase()})`, "", `${t.runId}: \`${r.run_id}\``, "");
    lines.push("```json", JSON.stringify(r.result, null, 2), "```", "");
    lines.push(`${t.dataKinds}: ` + Object.entries(r.data_kinds).map(([k, v]) => `${k} = ${v}`).join(", "));
    lines.push("", `${t.sources}:`);
    for (const s of r.sources) lines.push(`- ${s.id}${s.url ? ` (${s.url})` : ""}${s.retrieved_at ? `, ${t.retrieved} ${s.retrieved_at}` : ""}`);
    if (r.warnings.length) lines.push("", `${t.warnings}:`, ...r.warnings.map((w) => `- ${w}`));
    lines.push("");
  }
  return lines.join("\n");
}
