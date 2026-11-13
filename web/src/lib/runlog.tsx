import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session as AuthSession } from "@supabase/supabase-js";
import { callTool } from "@/api/client";
import type { Envelope, ToolName } from "@/api/types";
import type { SportTool } from "@/api/mockSport";
import { supabase } from "@/integrations/supabase/client";
import type { Tier } from "./tiers";

export interface LoggedRun {
  at: string;
  tier: Tier;
  env: Envelope;
}

interface Session {
  tier: Tier;
  /** Only in demo mode (no Lovable Cloud). With Cloud the tier comes from public.user_roles. */
  setTier: ((t: Tier) => void) | null;
  auth: AuthSession | null;
  runs: LoggedRun[];
  /** Calls a tool and records the run (session audit log and tool trace). */
  run: <R = Record<string, unknown>>(tool: ToolName | SportTool, inputs: Record<string, unknown>) => Promise<Envelope<R>>;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [tier, setTier] = useState<Tier>(supabase ? "citizen" : "office");
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [runs, setRuns] = useState<LoggedRun[]>([]);

  useEffect(() => {
    if (!supabase) return;
    const sb = supabase;
    const load = async (s: AuthSession | null) => {
      setAuth(s);
      if (!s) return setTier("citizen");
      // Read-only, for showing the right screens. The edge function decides the real tier.
      const { data } = await sb.from("user_roles").select("tier").eq("user_id", s.user.id).maybeSingle();
      setTier(data?.tier === "office" ? "office" : "citizen");
    };
    void sb.auth.getSession().then(({ data }) => load(data.session));
    const { data } = sb.auth.onAuthStateChange((_e, s) => void load(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const run = useCallback(
    async <R,>(tool: ToolName | SportTool, inputs: Record<string, unknown>) => {
      // The tier is not sent: the edge function takes it from the session.
      const env = await callTool<R>(tool, inputs);
      setRuns((r) => [{ at: new Date().toISOString(), tier, env: env as Envelope }, ...r].slice(0, 200));
      return env;
    },
    [tier],
  );
  const value = useMemo(() => ({ tier, setTier: supabase ? null : setTier, auth, runs, run }), [tier, auth, runs, run]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
