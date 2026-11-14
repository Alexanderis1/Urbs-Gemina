import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Database, FlaskConical, LogIn, Map as MapIcon, RadioTower, ShieldCheck, type LucideIcon } from "lucide-react";
import { Callout } from "@/components/ui";
import { supabase } from "@/integrations/supabase/client";
import { errorText } from "@/lib/errors";
import { useSession } from "@/lib/runlog";

const TOOLS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: MapIcon, title: "Full city console", text: "Every live layer, drawn areas, the last 24 hours and the evidence of each tool run." },
  { icon: RadioTower, title: "Permit check", text: "Context, field estimate and a cited report for a new antenna application." },
  { icon: FlaskConical, title: "Scenario lab", text: "What-if runs: floods, heat, road closures, chemical releases, new antennas." },
  { icon: Database, title: "Admin and audit", text: "Data providers, legal thresholds and the log of every run." },
];

/**
 * The door between the two experiences. Residents never need it; city personnel sign in here and land in the
 * operations workspace. The role is decided by the service (user_roles), never by this page.
 */
export default function StaffAccess() {
  const { setTier, auth } = useSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sb = supabase;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-4xl animate-rise-in gap-6 px-5 py-8 md:grid-cols-[1fr_1.1fr]">
        <section className="space-y-4">
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-semibold text-link hover:underline">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to the public service
          </Link>
          <div className="space-y-2">
            <p className="label flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              City administration
            </p>
            <h1 className="text-2xl font-bold leading-tight">City staff sign-in</h1>
            <p className="text-sm text-muted">
              The operations workspace is for Roma Capitale personnel. Residents do not need an account: everything public is on the other pages.
            </p>
          </div>

          {!sb ? (
            <div className="card space-y-3">
              <Callout tone="info" title="Demo">
                Sign-in is not connected in this copy, so the workspace opens without an account. Data the service reserves for staff stays
                reserved.
              </Callout>
              <button className="btn w-full" onClick={() => setTier?.("office")}>
                <LogIn className="h-4 w-4" aria-hidden="true" />
                Enter the staff workspace (demo)
              </button>
            </div>
          ) : auth ? (
            // Signed in, yet still on the public side: the account has no staff role.
            <div className="card space-y-3">
              <Callout tone="warn" title="This account is not registered as city staff">
                You are signed in, but the account has no staff role, so you see the public service. Ask the twin's administrator to add you.
              </Callout>
              <button className="btn-ghost w-full" onClick={() => void sb.auth.signOut()}>
                Sign out
              </button>
            </div>
          ) : sent ? (
            <Callout tone="info" title="Check your e-mail">
              We sent a sign-in link to {email}. Open it on this device to enter the workspace.
            </Callout>
          ) : (
            <form
              className="card space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                setError(null);
                void sb.auth
                  .signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } })
                  .then(({ error: err }) => (err ? setError(errorText(err)) : setSent(true)));
              }}
            >
              <label className="block space-y-1">
                <span className="block text-xs font-semibold">Work e-mail</span>
                <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@comune.roma.it" />
              </label>
              <button className="btn w-full">
                <LogIn className="h-4 w-4" aria-hidden="true" />
                Send me a sign-in link
              </button>
              <p className="hint">No password: the link in the e-mail signs you in. Only accounts with the staff role open the workspace.</p>
              {error && (
                <Callout tone="error" title="The link could not be sent">
                  {error}
                </Callout>
              )}
            </form>
          )}
        </section>

        <section aria-labelledby="staff-tools" className="space-y-3">
          <h2 id="staff-tools" className="text-base font-bold">
            What the workspace adds
          </h2>
          <ul className="space-y-2">
            {TOOLS.map((t) => (
              <li key={t.title} className="card flex items-start gap-3">
                <t.icon className="mt-0.5 h-5 w-5 shrink-0 text-link" aria-hidden="true" />
                <span>
                  <span className="block text-sm font-semibold">{t.title}</span>
                  <span className="block text-sm text-muted">{t.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
