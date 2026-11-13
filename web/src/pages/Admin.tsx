import { RunMeta } from "@/components/RunMeta";
import { useSession } from "@/lib/runlog";

export default function Admin() {
  const { runs } = useSession();
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Admin (office tier)</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card space-y-2">
          <h2 className="font-semibold">Data providers</h2>
          <p className="text-sm text-stone-600">
            Switch a layer between its simulated provider and the administration's own feed (for example{" "}
            <code>sim_register</code> to <code>pa</code>). Providers are selected in <code>config/providers.yaml</code>.
          </p>
          <p className="text-xs text-amber-700">Needs an admin endpoint on the tool API; requested from the tools workstream.</p>
        </div>
        <div className="card space-y-2">
          <h2 className="font-semibold">Legal thresholds</h2>
          <p className="text-sm text-stone-600">
            Thresholds live only in <code>config/thresholds.yaml</code>, each with its legal source and an "as of" date. This
            screen will show them read-only from the tool API.
          </p>
          <p className="text-xs text-amber-700">Needs a read endpoint on the tool API; requested from the tools workstream.</p>
        </div>
      </div>
      <div className="card space-y-2">
        <h2 className="font-semibold">Audit log (this session)</h2>
        {runs.length === 0 && <p className="text-sm text-stone-500">No tool runs yet.</p>}
        <ul className="divide-y divide-stone-100">
          {runs.map((r) => (
            <li key={`${r.at}-${r.env.run_id}`} className="py-2">
              <div className="text-xs text-stone-500">
                {r.at} · tier {r.tier}
              </div>
              <RunMeta env={r.env} compact />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
