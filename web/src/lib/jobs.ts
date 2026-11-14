// A request the live service cannot finish quickly (a cold start, a large simulation) does not fail any more:
// the service answers 202 with a job id and keeps working. The screen then reads the job every few seconds until
// it is done, and hands the result on as if it had arrived directly. Reading a job starts nothing, so it is cheap
// and safe to repeat; the run itself is still started only once.

/** One answer from the service: the HTTP status and the JSON body. */
export interface JobReply {
  status: number;
  body: unknown;
}

/** Pause between two readings. Basis: the service asks for 3 to 5 seconds (deploy note, 14 Nov 2026). */
export const JOB_POLL_MS = 4000;
/** Longest wait for one job. Basis: the heaviest scenario runs finish within a few minutes; after this the screen says so. */
export const JOB_MAX_WAIT_MS = 15 * 60_000;
/** Readings in a row that may go missing (connection hiccup, gateway error) before giving up. */
export const JOB_MAX_MISSES = 5;

export interface JobOptions {
  pollMs?: number;
  maxWaitMs?: number;
  maxMisses?: number;
  sleep?: (ms: number) => Promise<void>;
  /** Called once, when the answer turns out to be a job to wait for. */
  onRunning?: () => void;
}

/** Raised when waiting for a job ends without a result. Never worded like a missing answer (see lib/retry.ts). */
export class JobError extends Error {
  constructor(readonly code: "lost" | "timeout" | "unreachable") {
    super(`long run ${code}`);
    this.name = "JobError";
  }
}

const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const record = (v: unknown): Record<string, unknown> => (v !== null && typeof v === "object" ? (v as Record<string, unknown>) : {});

/** The address of a job, built from its id only (a path suggested by an answer is never followed). */
export function jobPath(jobId: unknown): string | null {
  return typeof jobId === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(jobId) ? `/jobs/${jobId}` : null;
}

/**
 * Turns a "still running" answer into the final one. Any other answer is returned untouched.
 * `read(path)` fetches the job; a finished job comes back as status 200 with the normal body, a failed one as
 * the status and `{ detail }` the service would have sent.
 */
export async function settleJob(first: JobReply, read: (path: string) => Promise<JobReply>, opts: JobOptions = {}): Promise<JobReply> {
  if (first.status !== 202) return first;
  const ticket = record(first.body);
  const path = ticket.status === "running" ? jobPath(ticket.job_id) : null;
  if (!path) return first;

  const pollMs = opts.pollMs ?? JOB_POLL_MS;
  const maxWaitMs = opts.maxWaitMs ?? JOB_MAX_WAIT_MS;
  const maxMisses = opts.maxMisses ?? JOB_MAX_MISSES;
  const sleep = opts.sleep ?? realSleep;
  opts.onRunning?.();

  let misses = 0;
  for (let waited = 0; waited < maxWaitMs; ) {
    await sleep(pollMs);
    waited += pollMs;
    let reply: JobReply;
    try {
      reply = await read(path);
    } catch {
      reply = { status: 0, body: null };
    }
    if (reply.status === 404) throw new JobError("lost");
    const job = record(reply.body);
    if (reply.status === 200 && job.status === "done") return { status: 200, body: job.result };
    if (reply.status === 200 && job.status === "error") {
      const code = typeof job.status_code === "number" ? job.status_code : 500;
      return { status: code, body: { detail: job.error } };
    }
    if (reply.status === 200 && job.status === "running") {
      misses = 0;
      continue;
    }
    misses += 1;
    if (misses >= maxMisses) throw new JobError("unreachable");
  }
  throw new JobError("timeout");
}
