import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Database, FlaskConical, LogIn, Map as MapIcon, RadioTower, ShieldCheck, type LucideIcon } from "lucide-react";
import { Callout } from "@/components/ui";
import { supabase } from "@/integrations/supabase/client";
import { errorText } from "@/lib/errors";
import { texts, tr } from "@/lib/i18n";
import { useSession } from "@/lib/runlog";

const T = texts({
  en: {
    tools: [
      { title: "Full city console", text: "Every live layer, drawn areas, the last 24 hours and the evidence of each tool run." },
      { title: "Permit check", text: "Context, field estimate and a cited report for a new antenna application." },
      { title: "Scenario lab", text: "What-if runs: floods, heat, road closures, chemical releases, new antennas." },
      { title: "Admin and audit", text: "Data providers, legal thresholds and the log of every run." },
    ],
    back: "Back to the public service",
    kicker: "City administration",
    title: "City staff sign-in",
    lead: "The operations workspace is for Roma Capitale personnel. Residents do not need an account: everything public is on the other pages.",
    demo: "Demo",
    demoText: "Sign-in is not connected in this copy, so the workspace opens without an account. Data the service reserves for staff stays reserved.",
    enterDemo: "Enter the staff workspace (demo)",
    noRole: "This account is not registered as city staff",
    noRoleText: "You are signed in, but the account has no staff role, so you see the public service. Ask the twin's administrator to add you.",
    signOut: "Sign out",
    checkMail: "Check your e-mail",
    sentTo: (email: string) => `We sent a sign-in link to ${email}. Open it on this device to enter the workspace.`,
    email: "Work e-mail",
    send: "Send me a sign-in link",
    noPassword: "No password: the link in the e-mail signs you in. Only accounts with the staff role open the workspace.",
    notSent: "The link could not be sent",
    adds: "What the workspace adds",
  },
  it: {
    tools: [
      { title: "Console completa della città", text: "Tutti i livelli live, le aree disegnate, le ultime 24 ore e le evidenze di ogni esecuzione." },
      { title: "Verifica istanza", text: "Contesto, stima del campo e relazione con fonti per una nuova istanza di antenna." },
      { title: "Laboratorio scenari", text: "Ipotesi da provare: alluvioni, caldo, chiusure stradali, rilasci chimici, nuove antenne." },
      { title: "Amministrazione e controllo", text: "Fornitori di dati, soglie di legge e registro di tutte le esecuzioni." },
    ],
    back: "Torna al servizio pubblico",
    kicker: "Amministrazione comunale",
    title: "Accesso personale del Comune",
    lead: "La sala operativa è riservata al personale di Roma Capitale. I cittadini non hanno bisogno di un account: tutto ciò che è pubblico è nelle altre pagine.",
    demo: "Demo",
    demoText: "In questa copia l'accesso non è collegato, quindi la sala operativa si apre senza account. I dati che il servizio riserva al personale restano riservati.",
    enterDemo: "Entra nella sala operativa (demo)",
    noRole: "Questo account non è registrato come personale del Comune",
    noRoleText: "Hai effettuato l'accesso, ma l'account non ha il ruolo del personale, quindi vedi il servizio pubblico. Chiedi all'amministratore del gemello di aggiungerti.",
    signOut: "Esci",
    checkMail: "Controlla la tua e-mail",
    sentTo: (email: string) => `Abbiamo inviato un link di accesso a ${email}. Aprilo su questo dispositivo per entrare nella sala operativa.`,
    email: "E-mail di lavoro",
    send: "Inviami un link di accesso",
    noPassword: "Nessuna password: il link nell'e-mail ti fa entrare. Solo gli account con il ruolo del personale aprono la sala operativa.",
    notSent: "Non è stato possibile inviare il link",
    adds: "Che cosa aggiunge la sala operativa",
  },
});

/** Icons of the four workspace tools, in the order of `T.tools`. */
const TOOL_ICONS: LucideIcon[] = [MapIcon, RadioTower, FlaskConical, Database];

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
  const t = tr(T);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-4xl animate-rise-in gap-6 px-5 py-8 md:grid-cols-[1fr_1.1fr]">
        <section className="space-y-4">
          <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-semibold text-link hover:underline">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            {t.back}
          </Link>
          <div className="space-y-2">
            <p className="label flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              {t.kicker}
            </p>
            <h1 className="text-2xl font-bold leading-tight">{t.title}</h1>
            <p className="text-sm text-muted">{t.lead}</p>
          </div>

          {!sb ? (
            <div className="card space-y-3">
              <Callout tone="info" title={t.demo}>
                {t.demoText}
              </Callout>
              <button className="btn w-full" onClick={() => setTier?.("office")}>
                <LogIn className="h-4 w-4" aria-hidden="true" />
                {t.enterDemo}
              </button>
            </div>
          ) : auth ? (
            // Signed in, yet still on the public side: the account has no staff role.
            <div className="card space-y-3">
              <Callout tone="warn" title={t.noRole}>
                {t.noRoleText}
              </Callout>
              <button className="btn-ghost w-full" onClick={() => void sb.auth.signOut()}>
                {t.signOut}
              </button>
            </div>
          ) : sent ? (
            <Callout tone="info" title={t.checkMail}>
              {t.sentTo(email)}
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
                <span className="block text-xs font-semibold">{t.email}</span>
                <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@comune.roma.it" />
              </label>
              <button className="btn w-full">
                <LogIn className="h-4 w-4" aria-hidden="true" />
                {t.send}
              </button>
              <p className="hint">{t.noPassword}</p>
              {error && (
                <Callout tone="error" title={t.notSent}>
                  {error}
                </Callout>
              )}
            </form>
          )}
        </section>

        <section aria-labelledby="staff-tools" className="space-y-3">
          <h2 id="staff-tools" className="text-base font-bold">
            {t.adds}
          </h2>
          <ul className="space-y-2">
            {t.tools.map((tool, i) => {
              const Icon = TOOL_ICONS[i]!;
              return (
                <li key={tool.title} className="card flex items-start gap-3">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-link" aria-hidden="true" />
                  <span>
                    <span className="block text-sm font-semibold">{tool.title}</span>
                    <span className="block text-sm text-muted">{tool.text}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}
