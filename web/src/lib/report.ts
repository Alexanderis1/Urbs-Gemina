import { envelopeBadge } from "@/api/envelope";
import type { Envelope } from "@/api/types";

// Client-side summary of the tool runs behind a permit check. The official cited report is built by
// the tool API (WS4); this file is the fallback download and never adds a number of its own.
export function buildCitedReport(address: string, runs: Envelope[]): string {
  const lines: string[] = [
    `# Permit context check: ${address}`,
    "",
    "Distances to sensitive sites are context, not a prohibition.",
    "Estimates are not measurements.",
    "",
  ];
  if (runs.some((r) => r.synthetic)) lines.push("> **SIMULATED**: this report contains synthetic data.", "");
  for (const r of runs) {
    lines.push(`## ${r.tool} (${envelopeBadge(r).toUpperCase()})`, "", `Run id: \`${r.run_id}\``, "");
    lines.push("```json", JSON.stringify(r.result, null, 2), "```", "");
    lines.push("Data kinds: " + Object.entries(r.data_kinds).map(([k, v]) => `${k} = ${v}`).join(", "));
    lines.push("", "Sources:");
    for (const s of r.sources) lines.push(`- ${s.id}${s.url ? ` (${s.url})` : ""}, retrieved ${s.retrieved_at}`);
    if (r.warnings.length) lines.push("", "Warnings:", ...r.warnings.map((w) => `- ${w}`));
    lines.push("");
  }
  return lines.join("\n");
}
