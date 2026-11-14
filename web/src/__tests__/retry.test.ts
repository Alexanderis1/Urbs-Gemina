import { describe, expect, it } from "vitest";
import { RETRY_WAITS_MS, callWithWakeUp, withRetry } from "@/lib/retry";

const net = () => new TypeError("Failed to fetch");
const noSleep = async () => {};

describe("withRetry", () => {
  it("tries again after a network failure and returns the first answer", async () => {
    let calls = 0;
    const waits: number[] = [];
    const out = await withRetry(
      async () => {
        calls += 1;
        if (calls < 3) throw net();
        return "ok";
      },
      { sleep: async (ms) => void waits.push(ms), onWait: () => {} },
    );
    expect(out).toBe("ok");
    expect(calls).toBe(3);
    expect(waits).toEqual(RETRY_WAITS_MS.slice(0, 2));
  });

  it("does not retry an answer from the server, only a missing one", async () => {
    let calls = 0;
    await expect(
      withRetry(
        async () => {
          calls += 1;
          throw new Error("query_layer failed: HTTP 422");
        },
        { sleep: noSleep },
      ),
    ).rejects.toThrow("HTTP 422");
    expect(calls).toBe(1);
  });

  it("gives up after the last wait and reports each wait", async () => {
    let calls = 0;
    const seen: number[] = [];
    await expect(
      withRetry(
        async () => {
          calls += 1;
          throw net();
        },
        { sleep: noSleep, onWait: (attempt) => void seen.push(attempt) },
      ),
    ).rejects.toThrow("Failed to fetch");
    expect(calls).toBe(RETRY_WAITS_MS.length + 1);
    expect(seen).toEqual(RETRY_WAITS_MS.map((_, i) => i + 1));
  });
});

describe("a call to a sleeping service", () => {
  it("is started at most twice: once, then once more after the service answers a light ping", async () => {
    let calls = 0;
    let pings = 0;
    const order: string[] = [];
    const out = await callWithWakeUp(
      async () => {
        calls += 1;
        order.push("run");
        if (calls === 1) throw net();
        return "result";
      },
      async () => {
        pings += 1;
        order.push("ping");
        if (pings < 2) throw net();
      },
      { sleep: noSleep },
    );
    expect(out).toBe("result");
    expect(order).toEqual(["run", "ping", "ping", "run"]);
  });

  it("is not repeated again and again when the call itself is what fails (a layer that crashes the service)", async () => {
    let calls = 0;
    await expect(
      callWithWakeUp(
        async () => {
          calls += 1;
          throw net();
        },
        async () => {},
        { sleep: noSleep },
      ),
    ).rejects.toThrow("Failed to fetch");
    expect(calls).toBe(2);
  });

  it("an answer from the server is final, and the service is not pinged", async () => {
    let pings = 0;
    await expect(
      callWithWakeUp(
        async () => {
          throw new Error("query_layer failed: HTTP 500");
        },
        async () => void (pings += 1),
        { sleep: noSleep },
      ),
    ).rejects.toThrow("HTTP 500");
    expect(pings).toBe(0);
  });
});
