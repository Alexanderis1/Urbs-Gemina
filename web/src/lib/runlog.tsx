import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { callTool } from "@/api/client";
import type { Envelope, ToolName } from "@/api/types";
import type { Tier } from "./tiers";

export interface LoggedRun {
  at: string;
  tier: Tier;
  env: Envelope;
}

interface Session {
  tier: Tier;
  setTier: (t: Tier) => void;
  runs: LoggedRun[];
  /** Calls a tool and records the run (session audit log and tool trace). */
  run: <R = Record<string, unknown>>(tool: ToolName, inputs: Record<string, unknown>) => Promise<Envelope<R>>;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [tier, setTier] = useState<Tier>("office");
  const [runs, setRuns] = useState<LoggedRun[]>([]);
  const run = useCallback(
    async <R,>(tool: ToolName, inputs: Record<string, unknown>) => {
      // The tier is not sent: the edge function takes it from the Supabase session.
      const env = await callTool<R>(tool, inputs);
      setRuns((r) => [{ at: new Date().toISOString(), tier, env: env as Envelope }, ...r].slice(0, 200));
      return env;
    },
    [tier],
  );
  const value = useMemo(() => ({ tier, setTier, runs, run }), [tier, runs, run]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
