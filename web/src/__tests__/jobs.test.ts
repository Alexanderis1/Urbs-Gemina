import { describe, expect, it } from "vitest";
import { isNetworkError } from "@/lib/errors";
import { jobPath, settleJob, type JobReply } from "@/lib/jobs";

const reply = (status: number, body: unknown): JobReply => ({ status, body });
const noSleep = async () => {};

/** A reader that hands out the given replies in order (an Error is thrown instead of returned). */
function reader(steps: (JobReply | Error)[]) {
  const paths: string[] = [];
  const read = async (path: string): Promise<JobReply> => {
    paths.push(path);
    const step = steps.shift();
    if (!step) throw new Error("no more replies");
    if (step instanceof Error) throw step;
    return step;
  };
  return { read, paths };
}

describe("slow requests come back as a job to wait for", () => {
  it("leaves a normal answer alone and reads nothing", async () => {
    const r = reader([]);
    const first = reply(200, { status: "ok", result: { n: 1 } });
    expect(await settleJob(first, r.read, { sleep: noSleep })).toBe(first);
    expect(r.paths).toEqual([]);
  });

  it("leaves an error answer alone", async () => {
    const r = reader([]);
    const first = reply(422, { detail: "bad input" });
    expect(await settleJob(first, r.read, { sleep: noSleep })).toBe(first);
  });

  it("waits for a running job and hands back its result as a normal answer", async () => {
    const r = reader([reply(200, { status: "running" }), reply(200, { status: "done", result: { text: "ready" } })]);
    const waits: number[] = [];
    const out = await settleJob(reply(202, { status: "running", job_id: "ab12-CD_3", poll: "/jobs/ab12-CD_3" }), r.read, {
      sleep: async (ms) => void waits.push(ms),
    });
    expect(out).toEqual({ status: 200, body: { text: "ready" } });
    expect(r.paths).toEqual(["/jobs/ab12-CD_3", "/jobs/ab12-CD_3"]);
    expect(waits).toEqual([4000, 4000]);
  });

  it("tells the screen once that a long run is in progress", async () => {
    const r = reader([reply(200, { status: "running" }), reply(200, { status: "done", result: {} })]);
    let told = 0;
    await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, { sleep: noSleep, onRunning: () => (told += 1) });
    expect(told).toBe(1);
  });

  it("hands back a failed job as the error answer the service would have sent", async () => {
    const r = reader([reply(200, { status: "error", status_code: 422, error: "place not found" })]);
    const out = await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, { sleep: noSleep });
    expect(out).toEqual({ status: 422, body: { detail: "place not found" } });
  });

  it("builds the address from the job id, never from a path the answer suggests", async () => {
    expect(jobPath("abc123")).toBe("/jobs/abc123");
    expect(jobPath("../admin")).toBeNull();
    expect(jobPath("")).toBeNull();
    const r = reader([reply(200, { status: "done", result: {} })]);
    await settleJob(reply(202, { status: "running", job_id: "j9", poll: "https://elsewhere.example/x" }), r.read, { sleep: noSleep });
    expect(r.paths).toEqual(["/jobs/j9"]);
  });

  it("leaves a 202 it does not understand alone", async () => {
    const r = reader([]);
    const first = reply(202, { status: "running", job_id: "../x" });
    expect(await settleJob(first, r.read, { sleep: noSleep })).toBe(first);
    expect(r.paths).toEqual([]);
  });

  it("keeps waiting through a few missed readings", async () => {
    const r = reader([new TypeError("Failed to fetch"), reply(502, {}), reply(200, { status: "done", result: { ok: true } })]);
    const out = await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, { sleep: noSleep });
    expect(out).toEqual({ status: 200, body: { ok: true } });
  });

  it("gives up after too many missed readings, without looking like a sleeping service", async () => {
    const miss = () => new TypeError("Failed to fetch");
    const r = reader([miss(), miss(), miss(), miss(), miss(), miss()]);
    const failure = await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, { sleep: noSleep }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    // A "no answer" error would make the client start the same run again; this one must not.
    expect(isNetworkError(failure)).toBe(false);
    expect(r.paths).toHaveLength(5);
  });

  it("stops when the service no longer knows the job", async () => {
    const r = reader([reply(404, { detail: "unknown job" })]);
    const failure = await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, { sleep: noSleep }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(isNetworkError(failure)).toBe(false);
    expect(r.paths).toHaveLength(1);
  });

  it("stops waiting after the longest wait", async () => {
    const r = reader([reply(200, { status: "running" }), reply(200, { status: "running" }), reply(200, { status: "running" })]);
    const failure = await settleJob(reply(202, { status: "running", job_id: "j1" }), r.read, {
      sleep: noSleep,
      pollMs: 1000,
      maxWaitMs: 3000,
    }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Error);
    expect(r.paths).toHaveLength(3);
  });
});
