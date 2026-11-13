import { useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useSession } from "@/lib/runlog";
import type { Tier } from "@/lib/tiers";

/** Header control: demo tier switch without Lovable Cloud, email sign-in with it. */
export function Account() {
  const { tier, setTier, auth } = useSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  if (!supabase) {
    return (
      <select
        className="rounded border border-stone-300 px-2 py-1 text-sm"
        value={tier}
        onChange={(e) => setTier?.(e.target.value as Tier)}
        title="Demo switch. With Lovable Cloud the tier comes from the user's role."
      >
        <option value="office">Office (demo)</option>
        <option value="citizen">Citizen (demo)</option>
      </select>
    );
  }
  const sb = supabase;
  if (auth) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="rounded bg-stone-100 px-2 py-1">{tier === "office" ? "Office" : "Citizen"}</span>
        <button className="btn-ghost" onClick={() => void sb.auth.signOut()}>
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
        <span className="text-xs text-stone-600">Check your e-mail for the sign-in link.</span>
      ) : (
        <>
          <span className="text-xs text-stone-500">Citizen view ·</span>
          <input className="input w-48" type="email" placeholder="Office e-mail" value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn">Sign in</button>
        </>
      )}
    </form>
  );
}
