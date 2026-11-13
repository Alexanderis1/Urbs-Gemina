import { envelopeBadge } from "@/api/envelope";
import type { Envelope } from "@/api/types";

// Client-side summary of the tool runs behind a permit check. The official cited report is built by
// the tool API (WS4); this file is the fallback download and never adds a number of its own.
export interface Application {
  operator?: string;
  height_m?: string;
  technology?: string;
  reference?: string;
}

export function buildCitedReport(address: string, runs: Envelope[], app: Application = {}): string {
  const lines: string[] = [
    `# Permit context check: ${address}`,
    "",
    "## Application (as entered by the officer)",
    "",
    `- Operator: ${app.operator || "not given"}`,
    `- Antenna height above ground: ${app.height_m ? `${app.height_m} m` : "not given"}`,
    `- Technology / bands: ${app.technology || "not given"}`,
    `- File reference: ${app.reference || "not given"}`,
    "",
    "Distances to sensitive sites are context, not a prohibition.",
    "Estimates are not measurements.",
    "",
  ];
  if (runs.some((r) => r.synthetic)) lines.push("> **SIMULATED**: this report uses simulated inputs (traffic loops or a what-if).", "");
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
