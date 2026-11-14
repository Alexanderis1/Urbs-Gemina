import { useState } from "react";
import { LogOut, UserRound } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useSession } from "@/lib/runlog";
import type { Tier } from "@/lib/tiers";

const FIELD =
  "min-h-8 rounded border border-chrome-line bg-chrome-deep px-2 text-xs text-chrome-ink placeholder:text-chrome-muted focus:border-white focus:outline-none";

/** Header control: demo tier switch without Lovable Cloud, email sign-in with it. */
export function Account() {
  const { tier, setTier, auth } = useSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  if (!supabase) {
    return (
      <label className="flex items-center gap-1.5 text-xs text-chrome-muted" title="Demo switch. With Lovable Cloud the tier comes from the user's role.">
        <UserRound className="h-4 w-4" aria-hidden="true" />
        <span className="sr-only">Access tier</span>
        <select className={`${FIELD} cursor-pointer pr-6 font-semibold`} value={tier} onChange={(e) => setTier?.(e.target.value as Tier)}>
          <option value="office">Office (demo)</option>
          <option value="citizen">Citizen (demo)</option>
        </select>
      </label>
    );
  }
  const sb = supabase;
  if (auth) {
    return (
      <div className="flex items-center gap-2 text-xs text-chrome-ink">
        <span className="flex items-center gap-1.5 rounded border border-chrome-line px-2 py-1 font-semibold">
          <UserRound className="h-4 w-4" aria-hidden="true" />
          {tier === "office" ? "Office" : "Citizen"}
        </span>
        <button className="inline-flex min-h-8 items-center gap-1.5 rounded px-2 font-semibold text-chrome-muted hover:bg-chrome-line hover:text-chrome-ink" onClick={() => void sb.auth.signOut()}>
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign out
        </button>
      </div>
    );
  }
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        void sb.auth.signInWithOtp({ email, options: { emailRedirectTo: window.location.origin } }).then(() => setSent(true));
      }}
    >
      {sent ? (
        <span className="text-xs text-chrome-muted">Check your e-mail for the sign-in link.</span>
      ) : (
        <>
          <span className="hidden text-xs text-chrome-muted xl:inline">Citizen view</span>
          <input className={`${FIELD} w-44`} type="email" aria-label="Office e-mail" placeholder="Office e-mail" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn btn-sm">Sign in</button>
        </>
      )}
    </form>
  );
}
