import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session as AuthSession } from "@supabase/supabase-js";
import { callTool, type CitizenTool } from "@/api/client";
import type { Envelope, ToolName } from "@/api/types";
import type { SportTool } from "@/api/mockSport";
import { supabase } from "@/integrations/supabase/client";
import { resolveTier, TIER_STORAGE_KEY, type Tier } from "./tiers";

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
  run: <R = Record<string, unknown>>(tool: ToolName | SportTool | CitizenTool, inputs: Record<string, unknown>) => Promise<Envelope<R>>;
}

const Ctx = createContext<Session | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(TIER_STORAGE_KEY);
  } catch {
    return null; // Storage can be blocked (private window): start on the public service.
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  // Everyone starts on the public service. Without Lovable Cloud (demo) the staff workspace is one click away
  // and the choice is remembered in this browser; with Cloud the tier comes from the signed-in user's role.
  const [tier, setTierState] = useState<Tier>(() => (supabase ? "citizen" : resolveTier(readStored())));
  const setTier = useCallback((t: Tier) => {
    setTierState(t);
    try {
      window.localStorage.setItem(TIER_STORAGE_KEY, t);
    } catch {
      // Not remembered; the choice still holds for this visit.
    }
  }, []);
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [runs, setRuns] = useState<LoggedRun[]>([]);

  useEffect(() => {
    if (!supabase) return;
    const sb = supabase;
    const load = async (s: AuthSession | null) => {
      setAuth(s);
      if (!s) return setTierState("citizen");
      // Read-only, for showing the right screens. The edge function decides the real tier.
      const { data } = await sb.from("user_roles").select("tier").eq("user_id", s.user.id).maybeSingle();
      setTierState(data?.tier === "office" ? "office" : "citizen");
    };
    void sb.auth.getSession().then(({ data }) => load(data.session));
    const { data } = sb.auth.onAuthStateChange((_e, s) => void load(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const run = useCallback(
    async <R,>(tool: ToolName | SportTool | CitizenTool, inputs: Record<string, unknown>) => {
      // The tier is not sent: the edge function takes it from the session.
      const env = await callTool<R>(tool, inputs);
      setRuns((r) => [{ at: new Date().toISOString(), tier, env: env as Envelope }, ...r].slice(0, 200));
      return env;
    },
    [tier],
  );
  const value = useMemo(() => ({ tier, setTier: supabase ? null : setTier, auth, runs, run }), [tier, setTier, auth, runs, run]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
