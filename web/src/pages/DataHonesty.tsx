import { useEffect, useMemo, useState } from "react";
import { Database } from "lucide-react";
import { KindBadge } from "@/components/Badge";
import { RunMeta } from "@/components/RunMeta";
import { Callout, Page, Segmented, Skeleton, Stat } from "@/components/ui";
import { useSession } from "@/lib/runlog";
import { KIND_META, type KindKey } from "@/lib/theme";
import type { DataKind, DataStatusResult, Envelope } from "@/api/types";
import { errorText } from "@/lib/errors";

// Order of the legend cards and of the stat tiles.
const KIND_ORDER: KindKey[] = ["real", "estimated", "simulated", "what_if", "not_available"];

type Filter = "all" | DataKind;
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "real", label: "Real" },
  { id: "estimated", label: "Estimated" },
  { id: "simulated", label: "Simulated" },
  { id: "not_available", label: "Not available" },
];

// Status words that mean the layer is being read right now.
// Statuses the tool returns today: active, needs_access, planned.
const isLive = (status: string) => status === "active" || status === "ok" || status.startsWith("live") || status.startsWith("available");

export default function DataHonesty() {
  const { run } = useSession();
  const [env, setEnv] = useState<Envelope<DataStatusResult> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    run<DataStatusResult>("data_status", {}).then(setEnv, (e: unknown) => setError(errorText(e)));
  }, [run]);

  const layers = useMemo(() => env?.result.layers ?? [], [env]);

  // Counts for the stat tiles, taken from all rows (not from the filter).
  const counts = useMemo(() => {
    const c: Record<DataKind, number> = { real: 0, estimated: 0, simulated: 0, not_available: 0, hypothetical: 0 };
    for (const l of layers) c[l.data_kind] += 1;
    return c;
  }, [layers]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return layers.filter((l) => {
      if (filter !== "all" && l.data_kind !== filter) return false;
      if (!q) return true;
      return l.layer.toLowerCase().includes(q) || l.layer.replace(/_/g, " ").toLowerCase().includes(q) || l.provider.toLowerCase().includes(q);
    });
  }, [layers, filter, query]);

  const statTiles: { kind: DataKind; label: string; tone: "real" | "estimated" | "simulated" | "ink" }[] = [
    { kind: "real", label: "Real", tone: "real" },
    { kind: "estimated", label: "Estimated", tone: "estimated" },
    { kind: "simulated", label: "Simulated", tone: "simulated" },
    { kind: "not_available", label: "Not available", tone: "ink" },
  ];

  return (
    <Page
      title="Data honesty"
      icon={Database}
      lead="Every layer says where it comes from and how far to trust it."
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {KIND_ORDER.map((key) => (
          <div key={key} className="card space-y-2">
            {key === "what_if" ? (
              <KindBadge kind="simulated" text="what-if" size="md" />
            ) : (
              <KindBadge kind={key} size="md" />
            )}
            <p className="hint">{KIND_META[key].hint}</p>
          </div>
        ))}
      </div>

      {error && (
        <Callout tone="error" title="Could not load the data status">
          {error}
        </Callout>
      )}

      {!env && !error && (
        <div className="card">
          <Skeleton lines={6} />
        </div>
      )}

      {env && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Layers" value={layers.length} />
            {statTiles
              .filter((t) => counts[t.kind] > 0)
              .map((t) => (
                <Stat key={t.kind} label={t.label} value={counts[t.kind]} tone={t.tone} />
              ))}
          </div>

          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <Segmented value={filter} onChange={setFilter} options={FILTERS} label="Filter by kind" />
            <input
              type="search"
              className="input max-w-xs"
              aria-label="Search layers"
              placeholder="Search layers or providers"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <div className="card overflow-x-auto p-0">
            <table className="table">
              <thead>
                <tr>
                  <th>Layer</th>
                  <th>Kind</th>
                  <th>Provider</th>
                  <th>Status</th>
                  <th>Licence</th>
                  <th>Updates</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((l) => {
                  const live = isLive(l.status);
                  return (
                    <tr key={l.layer}>
                      <td className="font-semibold">{l.layer.replace(/_/g, " ")}</td>
                      <td>
                        <KindBadge kind={l.data_kind} />
                      </td>
                      <td>{l.provider}</td>
                      <td className="whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5">
                          <span className={`h-2 w-2 shrink-0 rounded-full ${live ? "bg-real" : "bg-muted"}`} aria-hidden="true" />
                          {l.status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="text-xs">{l.licence ?? "—"}</td>
                      <td className="whitespace-nowrap text-xs">{l.cadence ?? "—"}</td>
                      <td className="text-xs text-muted">{l.notes ?? "—"}</td>
                    </tr>
                  );
                })}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={7} className="hint text-center">
                      No layers match.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="border-t border-line p-4">
              <RunMeta env={env} />
            </div>
          </div>
        </>
      )}
    </Page>
  );
}
