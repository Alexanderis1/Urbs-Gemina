import type { ReactNode } from "react";
import { Plug, ScrollText, Scale, Settings2, type LucideIcon } from "lucide-react";
import { badgeText, envelopeBadge } from "@/api/envelope";
import { KindBadge } from "@/components/Badge";
import { Callout, EmptyState, Page } from "@/components/ui";
import { shortId } from "@/lib/format";
import { useSession } from "@/lib/runlog";
import { getLang, locale, texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    title: "Admin",
    lead: "Office tier. Providers, legal thresholds and the audit log of this session.",
    notConnected: "Not connected yet",
    providers: "Data providers",
    providersNote: "Needs an admin endpoint on the tool API; requested from the tools workstream.",
    providersBody: (
      <>
        Switch a layer between its simulated provider and the administration's own feed (for example <code>sim_register</code> to <code>pa</code>).
        Providers are selected in <code>config/providers.yaml</code>.
      </>
    ),
    thresholds: "Legal thresholds",
    thresholdsNote: "Needs a read endpoint on the tool API; requested from the tools workstream.",
    thresholdsBody: (
      <>
        Thresholds live only in <code>config/thresholds.yaml</code>, each with its legal source and an "as of" date. This screen will show them
        read-only from the tool API.
      </>
    ),
    audit: "Audit log (this session)",
    auditHint: "Every tool run, newest first. Kept in this browser only.",
    noRuns: "No tool runs yet",
    noRunsHint: "Open a screen and run a tool; each run is listed here with its id.",
    time: "Time",
    tier: "Tier",
    tool: "Tool",
    runId: "Run id",
    label: "Label",
    status: "Status",
    warnings: "Warnings",
  },
  it: {
    title: "Amministrazione",
    lead: "Profilo del personale. Fonti dei dati, soglie di legge e registro delle esecuzioni di questa sessione.",
    notConnected: "Non ancora collegato",
    providers: "Fonti dei dati",
    providersNote: "Serve un endpoint di amministrazione sull'API degli strumenti; è stato chiesto al gruppo degli strumenti.",
    providersBody: (
      <>
        Passa un livello dalla sua fonte simulata ai dati propri dell'amministrazione (per esempio da <code>sim_register</code> a <code>pa</code>).
        Le fonti si scelgono in <code>config/providers.yaml</code>.
      </>
    ),
    thresholds: "Soglie di legge",
    thresholdsNote: "Serve un endpoint di lettura sull'API degli strumenti; è stato chiesto al gruppo degli strumenti.",
    thresholdsBody: (
      <>
        Le soglie stanno solo in <code>config/thresholds.yaml</code>, ognuna con la sua fonte di legge e una data "alla data del". Questa
        schermata le mostrerà in sola lettura dall'API degli strumenti.
      </>
    ),
    audit: "Registro delle esecuzioni (questa sessione)",
    auditHint: "Ogni esecuzione di uno strumento, dalla più recente. Resta solo in questo browser.",
    noRuns: "Nessuna esecuzione ancora",
    noRunsHint: "Apri una schermata ed esegui uno strumento: ogni esecuzione compare qui con il suo id.",
    time: "Ora",
    tier: "Profilo",
    tool: "Strumento",
    runId: "Id esecuzione",
    label: "Etichetta",
    status: "Stato",
    warnings: "Avvisi",
  },
});

function ConnectionCard({ icon: Icon, title, children, note }: { icon: LucideIcon; title: string; children: ReactNode; note: string }) {
  return (
    <section className="card space-y-3">
      <h2 className="flex items-center gap-2 text-base font-bold">
        <Icon className="h-4 w-4 text-link" aria-hidden="true" />
        {title}
      </h2>
      <p className="text-sm">{children}</p>
      <Callout tone="info" title={tr(T).notConnected}>
        {note}
      </Callout>
    </section>
  );
}

export default function Admin() {
  const { runs } = useSession();
  const t = tr(T);
  return (
    <Page
      title={t.title}
      icon={Settings2}
      lead={t.lead}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <ConnectionCard
          icon={Plug}
          title={t.providers}
          note={t.providersNote}
        >
          {t.providersBody}
        </ConnectionCard>
        <ConnectionCard
          icon={Scale}
          title={t.thresholds}
          note={t.thresholdsNote}
        >
          {t.thresholdsBody}
        </ConnectionCard>
      </div>

      <section className="card overflow-x-auto p-0">
        <header className="px-4 py-3">
          <h2 className="flex items-center gap-2 text-base font-bold">
            <ScrollText className="h-4 w-4 text-link" aria-hidden="true" />
            {t.audit}
          </h2>
          <p className="hint mt-0.5">{t.auditHint}</p>
        </header>
        {runs.length === 0 ? (
          <div className="p-4">
            <EmptyState icon={ScrollText} title={t.noRuns}>
              {t.noRunsHint}
            </EmptyState>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t.time}</th>
                <th>{t.tier}</th>
                <th>{t.tool}</th>
                <th>{t.runId}</th>
                <th>{t.label}</th>
                <th>{t.status}</th>
                <th>{t.warnings}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={`${r.at}-${r.env.run_id}`}>
                  <td className="num whitespace-nowrap">{new Date(r.at).toLocaleTimeString(getLang() === "it" ? locale() : undefined)}</td>
                  <td>{r.tier}</td>
                  <td>
                    <code>{r.env.tool}</code>
                  </td>
                  <td>
                    <code title={r.env.run_id}>{shortId(r.env.run_id)}</code>
                  </td>
                  <td>
                    <KindBadge kind={envelopeBadge(r.env)} text={badgeText(r.env)} />
                  </td>
                  <td>{r.env.status ?? "ok"}</td>
                  <td className="num">{r.env.warnings.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </Page>
  );
}
