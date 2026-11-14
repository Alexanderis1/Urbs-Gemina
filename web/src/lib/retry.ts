// The live service sleeps when nobody uses it (it must not cost money while idle). The first request after a
// pause can go unanswered while it wakes up; once awake it answers in under a second. So a missing answer is
// retried, and the screen says what is happening instead of showing a failure.

import { isNetworkError } from "@/lib/errors";

/** Pauses between tries. Basis: waking takes about two and a half minutes (measured 14 Nov 2026). */
export const RETRY_WAITS_MS: readonly number[] = [4000, 20000, 40000, 60000, 60000];

/** Tools that start a simulation or a long estimate. They are never started more than twice. */
export const HEAVY_TOOLS: readonly string[] = ["run_scenario", "estimate_field", "permit_report"];

export function isHeavyTool(tool: string): boolean {
  return HEAVY_TOOLS.includes(tool);
}

export interface RetryOptions {
  waits?: readonly number[];
  /** Called before each pause with the number of the try that just failed (1 = the first). */
  onWait?: (attempt: number, waitMs: number) => void;
  sleep?: (ms: number) => Promise<void>;
}

const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Runs `fn`; when no answer arrives (network failure) waits and tries again. Server answers are never retried. */
export async function withRetry<T>(fn: () => Promise<T>, opts: RetryOptions = {}): Promise<T> {
  const waits = opts.waits ?? RETRY_WAITS_MS;
  const sleep = opts.sleep ?? realSleep;
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await fn();
    } catch (e) {
      const wait = waits[attempt - 1];
      if (!isNetworkError(e) || wait === undefined) throw e;
      opts.onWait?.(attempt, wait);
      await sleep(wait);
    }
  }
}

/**
 * A light call is retried as is. A heavy call is not repeated blindly (that would start the simulation again and
 * again): after a missing answer the service is woken with a light `ping`, then the heavy call runs once more.
 */
export async function callWithWakeUp<T>(tool: string, call: () => Promise<T>, ping: () => Promise<void>, opts: RetryOptions = {}): Promise<T> {
  if (!isHeavyTool(tool)) return withRetry(call, opts);
  try {
    return await call();
  } catch (e) {
    if (!isNetworkError(e)) throw e;
    opts.onWait?.(1, 0);
    await withRetry(ping, opts);
    return call();
  }
}
