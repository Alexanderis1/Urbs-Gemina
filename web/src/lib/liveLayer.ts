// Heavy layers open at once: the last answer saved in this browser is shown immediately with the time of its data,
// the live data is asked in the background, and the LIVE badge appears when it arrives. When the data gets too old
// the badge goes and the layer is asked again. Nothing is asked while the page is not on screen (no wasted compute).
// Pure logic, no React and no browser storage: see lib/layerStore.ts and lib/useLive.ts. Reasoning: design-system decision 32.

const MIN = 60_000;

/**
 * How long an answer counts as live, in minutes. After that the LIVE badge goes and the layer is asked again.
 * All four are assumptions, to be tuned with the people who run the service.
 */
const FRESHNESS: { minutes: number; layers: string[]; basis: string }[] = [
  {
    minutes: 5,
    layers: ["transit", "transit_delay", "road_speed", "traffic_flow", "micromobility", "activity"],
    basis: "bus, traffic and shared-vehicle feeds are republished every minute or so; five minutes keeps the map current without waking the service for every glance",
  },
  {
    minutes: 10,
    layers: ["rain"],
    basis: "rain moves fast; ten minutes is about the pace of new radar images",
  },
  {
    minutes: 30,
    layers: ["air_no2", "air_pm10", "air_pm25", "air_o3", "air_temperature", "air_quality", "air_quality_citizen", "air_quality_model", "emf"],
    basis: "stations and the European air model publish hourly, and the service rebuilds these layers at most every 30 minutes (config/tools.yaml, citizen.cache_minutes)",
  },
  {
    minutes: 12 * 60,
    layers: ["hospitals", "schools_state", "health_care", "care_homes_osm", "playgrounds_osm", "nidi", "infanzia", "antenna_register", "emf_baseline", "masts_osm"],
    basis: "registers of places change over weeks, not hours",
  },
];
/** Any other layer. Basis: assumption, between the live feeds and the hourly layers. */
const DEFAULT_MINUTES = 15;

export function maxAgeMs(layer: string | null): number {
  const group = layer ? FRESHNESS.find((g) => g.layers.includes(layer)) : undefined;
  return (group?.minutes ?? DEFAULT_MINUTES) * MIN;
}

/**
 * Layers that are asked every time and never kept in the browser: their sources may not be passed on
 * (data/manifest.json, redistribution: false: the Cartoradio grid and the estimated antenna register), and
 * single measurements are for the office only (config/tools.yaml, office_only_detail_layers).
 */
const NEVER_SAVED: readonly string[] = ["emf_baseline", "antenna_register", "emf_measurements"];

export function savable(layer: string | null): boolean {
  return !!layer && !NEVER_SAVED.includes(layer);
}

/** One name per question, whatever the order of its parts. The access tier is always a part: saved answers never cross tiers. */
export function cacheKey(parts: Record<string, unknown>): string {
  const sorted = (v: unknown): unknown =>
    Array.isArray(v)
      ? v.map(sorted)
      : v && typeof v === "object"
        ? Object.fromEntries(
            Object.keys(v as Record<string, unknown>)
              .sort()
              .map((k) => [k, sorted((v as Record<string, unknown>)[k])]),
          )
        : v;
  return JSON.stringify(sorted(parts));
}

export interface Saved<T = unknown> {
  /** When the answer arrived from the service (milliseconds). */
  at: number;
  value: T;
}

export interface LiveStore {
  get(key: string): Promise<Saved | null>;
  set(key: string, saved: Saved): Promise<void>;
  clear(): Promise<void>;
}

/** Keeps answers for this visit only: used where the browser has no storage, and in tests. */
export function memoryStore(): LiveStore {
  const kept = new Map<string, Saved>();
  return {
    get: async (key) => kept.get(key) ?? null,
    set: async (key, saved) => void kept.set(key, saved),
    clear: async () => kept.clear(),
  };
}

/**
 * loading = nothing to show yet · refreshing = a saved copy is on screen while the live data loads ·
 * live = the data on screen is within its life · saved = the live request failed, the saved copy stays · error = nothing to show.
 */
export type LivePhase = "loading" | "refreshing" | "live" | "saved" | "error";

export interface LiveState<T> {
  value: T | null;
  /** When the data on screen arrived from the service. */
  at: number | null;
  phase: LivePhase;
  error: string | null;
}

export interface LiveOptions<T> {
  maxAgeMs: number;
  store: LiveStore;
  /** False for an answer that is not data (a refusal): shown, not saved, not repeated. */
  keep?: (value: T) => boolean;
  /** Is the page on screen? Nothing is asked again while it is not. */
  visible?: () => boolean;
  /** Calls back when the page is on screen again; returns how to stop listening. */
  onVisible?: (cb: () => void) => () => void;
  errorText?: (e: unknown) => string;
}

/** Follows one question: tells `emit` what to show now and every time that changes. Returns how to stop. */
export function watchLive<T>(key: string, load: () => Promise<T>, opts: LiveOptions<T>, emit: (state: LiveState<T>) => void): () => void {
  const { maxAgeMs: maxAge, store } = opts;
  const keep = opts.keep ?? (() => true);
  const visible = opts.visible ?? (() => true);
  const text = opts.errorText ?? ((e: unknown) => (e instanceof Error ? e.message : String(e)));
  let stopped = false;
  let shown: Saved<T> | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let offVisible: (() => void) | undefined;

  const later = (ms: number) => {
    clearTimeout(timer);
    timer = setTimeout(tooOld, Math.max(0, ms));
  };

  function tooOld() {
    if (stopped) return;
    if (visible()) return void refresh();
    // Nobody is looking: wait for the page to come back instead of asking the service.
    offVisible?.();
    offVisible = opts.onVisible?.(() => {
      offVisible?.();
      offVisible = undefined;
      tooOld();
    });
  }

  async function refresh() {
    emit({ value: shown?.value ?? null, at: shown?.at ?? null, phase: shown ? "refreshing" : "loading", error: null });
    try {
      const value = await load();
      if (stopped) return;
      const at = Date.now();
      if (keep(value)) {
        shown = { at, value };
        void store.set(key, shown).catch(() => undefined);
        later(maxAge);
      } else shown = null;
      emit({ value, at, phase: "live", error: null });
    } catch (e) {
      if (stopped) return;
      emit({ value: shown?.value ?? null, at: shown?.at ?? null, phase: shown ? "saved" : "error", error: text(e) });
      // With a copy on screen, try again after one more life; with nothing to show, the person asks again.
      if (shown) later(maxAge);
    }
  }

  void store
    .get(key)
    .catch(() => null)
    .then((saved) => {
      if (stopped) return;
      if (saved) {
        shown = saved as Saved<T>;
        const age = Date.now() - saved.at;
        if (age >= 0 && age < maxAge) {
          emit({ value: shown.value, at: shown.at, phase: "live", error: null });
          return later(maxAge - age);
        }
      }
      void refresh();
    });

  return () => {
    stopped = true;
    clearTimeout(timer);
    offVisible?.();
  };
}
