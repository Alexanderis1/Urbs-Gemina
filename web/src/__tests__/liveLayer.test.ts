import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cacheKey, maxAgeMs, memoryStore, savable, watchLive, type LiveState } from "@/lib/liveLayer";

const MIN = 60_000;

describe("the saved copy of a layer", () => {
  it("names a question the same way whatever the order of its parts", () => {
    expect(cacheKey({ layer: "air_no2", area: "city", tier: "office" })).toBe(cacheKey({ tier: "office", area: "city", layer: "air_no2" }));
    expect(cacheKey({ layer: "air_no2", tier: "office" })).not.toBe(cacheKey({ layer: "air_no2", tier: "citizen" }));
  });

  it("gives live feeds a short life and registers a long one", () => {
    expect(maxAgeMs("transit_delay")).toBeLessThan(maxAgeMs("air_no2"));
    expect(maxAgeMs("air_no2")).toBeLessThan(maxAgeMs("hospitals"));
    expect(maxAgeMs("something_new")).toBeGreaterThan(0);
  });

  it("never saves the layers that may not be passed on (Cartoradio grid, antenna register)", () => {
    expect(savable("emf_baseline")).toBe(false);
    expect(savable("antenna_register")).toBe(false);
    expect(savable("emf_measurements")).toBe(false);
    expect(savable("air_no2")).toBe(true);
  });
});

describe("showing the saved copy first, then the live data", () => {
  beforeEach(() => vi.useFakeTimers({ now: new Date("2026-11-14T09:00:00Z") }));
  afterEach(() => vi.useRealTimers());

  const settle = () => vi.advanceTimersByTimeAsync(0);
  const watch = (load: () => Promise<string>, store = memoryStore(), extra: { visible?: () => boolean; onVisible?: (cb: () => void) => () => void } = {}) => {
    const seen: LiveState<string>[] = [];
    const stop = watchLive<string>("k", load, { maxAgeMs: 10 * MIN, store, ...extra }, (s) => seen.push(s));
    return { seen, stop, store };
  };

  it("with nothing saved: loads, then shows the answer as live and saves it", async () => {
    const { seen, store } = watch(async () => "fresh");
    await settle();
    expect(seen.map((s) => s.phase)).toEqual(["loading", "live"]);
    expect(seen[1]).toMatchObject({ value: "fresh", at: Date.now() });
    expect(await store.get("k")).toEqual({ at: Date.now(), value: "fresh" });
  });

  it("with an old copy saved: shows it at once with its time, says it is loading, then switches to live", async () => {
    const store = memoryStore();
    const savedAt = Date.now() - 45 * MIN;
    await store.set("k", { at: savedAt, value: "old" });
    const { seen } = watch(async () => "fresh", store);
    await settle();
    expect(seen[0]).toMatchObject({ value: "old", at: savedAt, phase: "refreshing" });
    expect(seen[1]).toMatchObject({ value: "fresh", phase: "live" });
  });

  it("with a recent copy saved: it is live already and the service is not asked", async () => {
    const store = memoryStore();
    await store.set("k", { at: Date.now() - 2 * MIN, value: "recent" });
    const load = vi.fn(async () => "fresh");
    const { seen } = watch(load, store);
    await settle();
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ value: "recent", phase: "live" });
    expect(load).not.toHaveBeenCalled();
  });

  it("when the data gets too old: the live badge goes and the service is asked again", async () => {
    let n = 0;
    const load = vi.fn(async () => `answer ${++n}`);
    const { seen } = watch(load);
    await settle();
    await vi.advanceTimersByTimeAsync(10 * MIN);
    expect(load).toHaveBeenCalledTimes(2);
    expect(seen.map((s) => s.phase)).toEqual(["loading", "live", "refreshing", "live"]);
    expect(seen[2]!.value).toBe("answer 1");
    expect(seen[3]!.value).toBe("answer 2");
  });

  it("does not ask again while nobody is looking, and asks as soon as the page is seen again", async () => {
    let visible = true;
    let back: (() => void) | null = null;
    const load = vi.fn(async () => "x");
    watch(load, memoryStore(), { visible: () => visible, onVisible: (cb) => ((back = cb), () => (back = null)) });
    await settle();
    visible = false;
    await vi.advanceTimersByTimeAsync(60 * MIN);
    expect(load).toHaveBeenCalledTimes(1);
    visible = true;
    back!();
    await settle();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("when the live request fails: keeps the saved copy on screen and says so; with nothing saved it is an error", async () => {
    const store = memoryStore();
    await store.set("k", { at: Date.now() - 45 * MIN, value: "old" });
    const failing = watch(async () => Promise.reject(new Error("down")), store);
    await settle();
    expect(failing.seen.at(-1)).toMatchObject({ value: "old", phase: "saved", error: "down" });

    const empty = watch(async () => Promise.reject(new Error("down")));
    await settle();
    expect(empty.seen.at(-1)).toMatchObject({ value: null, phase: "error", error: "down" });
  });

  it("does not save an answer that is not data (a refusal), and does not repeat it", async () => {
    const store = memoryStore();
    const seen: LiveState<string>[] = [];
    const load = vi.fn(async () => "refused");
    watchLive<string>("k", load, { maxAgeMs: 10 * MIN, store, keep: (v) => v !== "refused" }, (s) => seen.push(s));
    await settle();
    await vi.advanceTimersByTimeAsync(30 * MIN);
    expect(await store.get("k")).toBeNull();
    expect(load).toHaveBeenCalledTimes(1);
    expect(seen.at(-1)).toMatchObject({ value: "refused", phase: "live" });
  });

  it("says nothing more once stopped", async () => {
    const { seen, stop } = watch(async () => "fresh");
    stop();
    await vi.advanceTimersByTimeAsync(30 * MIN);
    expect(seen.filter((s) => s.phase === "live")).toHaveLength(0);
  });
});
