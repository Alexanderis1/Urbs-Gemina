import type { ReactNode } from "react";
import { Plug, ScrollText, Scale, Settings2, type LucideIcon } from "lucide-react";
import { badgeText, envelopeBadge } from "@/api/envelope";
import { KindBadge } from "@/components/Badge";
import { Callout, EmptyState, Page } from "@/components/ui";
import { shortId } from "@/lib/format";
import { useSession } from "@/lib/runlog";

function ConnectionCard({ icon: Icon, title, children, note }: { icon: LucideIcon; title: string; children: ReactNode; note: string }) {
  return (
    <section className="card space-y-3">
      <h2 className="flex items-center gap-2 text-base font-bold">
        <Icon className="h-4 w-4 text-link" aria-hidden="true" />
        {title}
      </h2>
      <p className="text-sm">{children}</p>
      <Callout tone="info" title="Not connected yet">
        {note}
      </Callout>
    </section>
  );
}

export default function Admin() {
  const { runs } = useSession();
  return (
    <Page
      title="Admin"
      icon={Settings2}
      lead="Office tier. Providers, legal thresholds and the audit log of this session."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <ConnectionCard
          icon={Plug}
          title="Data providers"
          note="Needs an admin endpoint on the tool API; requested from the tools workstream."
        >
          Switch a layer between its simulated provider and the administration's own feed (for example{" "}
          <code>sim_register</code> to <code>pa</code>). Providers are selected in <code>config/providers.yaml</code>.
        </ConnectionCard>
        <ConnectionCard
          icon={Scale}
          title="Legal thresholds"
          note="Needs a read endpoint on the tool API; requested from the tools workstream."
        >
          Thresholds live only in <code>config/thresholds.yaml</code>, each with its legal source and an "as of" date. This
          screen will show them read-only from the tool API.
        </ConnectionCard>
      </div>

      <section className="card overflow-x-auto p-0">
        <header className="px-4 py-3">
          <h2 className="flex items-center gap-2 text-base font-bold">
            <ScrollText className="h-4 w-4 text-link" aria-hidden="true" />
            Audit log (this session)
          </h2>
          <p className="hint mt-0.5">Every tool run, newest first. Kept in this browser only.</p>
        </header>
        {runs.length === 0 ? (
          <div className="p-4">
            <EmptyState icon={ScrollText} title="No tool runs yet">
              Open a screen and run a tool; each run is listed here with its id.
            </EmptyState>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Tier</th>
                <th>Tool</th>
                <th>Run id</th>
                <th>Label</th>
                <th>Status</th>
                <th>Warnings</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={`${r.at}-${r.env.run_id}`}>
                  <td className="num whitespace-nowrap">{new Date(r.at).toLocaleTimeString()}</td>
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
