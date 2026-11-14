// Data for the citizen screens. Each hook asks the purpose-built citizen tool first and, when the live service
// does not carry it (yet), falls back to the layer tools so the screen still shows real twin data.
import { useEffect, useState } from "react";
import type { CitizenTool } from "@/api/client";
import { isOk } from "@/api/envelope";
import type { DataKind, Envelope } from "@/api/types";
import { errorText } from "@/lib/errors";
import {
  aroundPolygon,
  coarseCells,
  nearestCell,
  parseAirHere,
  parseCityHeatmap,
  parseEmfHere,
  parsePlacesOpen,
  parseTransportNow,
  placesFromFacilities,
  type CityHeatmap,
  type HereAnswer,
  type OpenPlace,
  type TransportEvent,
  type FeedState,
} from "@/lib/here";
import { metricInfo, normalizeLayer } from "@/lib/layers";
import { cacheKey, maxAgeMs, savable, type LiveState } from "@/lib/liveLayer";
import { useLive } from "@/lib/useLive";
import { useSession } from "@/lib/runlog";

export type Loaded<T> =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ok";
      data: T;
      env: Envelope;
      kind?: DataKind;
      /** True when the layer tools answered instead of the citizen tool. */
      fallback: boolean;
      /** How fresh the data is, for answers that are saved in the browser and shown at once (lib/liveLayer.ts). */
      live?: Pick<LiveState<unknown>, "phase" | "at">;
    }
  /** The live service does not offer this yet. */
  | { status: "missing" }
  | { status: "error"; text: string };

/** Citizen tools the service said it does not have: not asked again in this visit (every call costs a request). */
const missing = new Set<CitizenTool>();

type Run = ReturnType<typeof useSession>["run"];

async function ask(run: Run, tool: CitizenTool, inputs: Record<string, unknown>): Promise<Envelope | null> {
  if (missing.has(tool)) return null;
  try {
    const env = (await run(tool, inputs)) as Envelope;
    return isOk(env) ? env : null;
  } catch (e) {
    const text = e instanceof Error ? e.message : String(e);
    if (/not found|unknown route|404|not in the sample data/i.test(text)) missing.add(tool);
    return null;
  }
}

const firstKind = (env: Envelope, layer?: string): DataKind | undefined => (layer && env.data_kinds[layer]) || Object.values(env.data_kinds)[0];

/** Runs `load` again whenever `key` changes; an answer for an old key is dropped. `key = null` waits. */
function useLoaded<T>(key: string | null, load: () => Promise<Loaded<T>>): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ status: "idle" });
  useEffect(() => {
    if (key === null) return setState({ status: "idle" });
    let live = true;
    setState({ status: "loading" });
    load()
      .then((s) => live && setState(s))
      .catch((e: unknown) => live && setState({ status: "error", text: errorText(e) }));
    return () => {
      live = false;
    };
    // `load` is rebuilt on every render; `key` says when the question changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

/** The whole city for one layer, as patches. `time` in the future asks for a prediction where the tool has one. */
export function useHeatmap(layer: string | null, time: string | null = null): Loaded<CityHeatmap> {
  const { run, tier } = useSession();
  type Answer = Extract<Loaded<CityHeatmap>, { status: "ok" | "missing" }>;
  // The whole city is the heaviest question of the citizen screens: the last answer shows at once, then the live one.
  const live = useLive<Answer>(
    layer && cacheKey({ what: "city_heatmap", tier, layer, time }),
    async () => {
      const env = await ask(run, "city_heatmap", { layer, ...(time ? { time } : {}) });
      if (env) {
        const data = parseCityHeatmap(env.result);
        if (data.cells.length) return { status: "ok", data, env, kind: firstKind(env, layer!), fallback: false };
      }
      // The layer tool thins a whole-city answer evenly; merged into larger hexagons it covers the city again.
      const raw = (await run("query_layer", { layer, area: "city", time, limit: 5000 })) as Envelope;
      if (!isOk(raw)) return { status: "missing" };
      const fine = normalizeLayer(raw.result);
      const data: CityHeatmap = { cells: coarseCells(fine.items, 7), legend: [], unit: fine.unit };
      return data.cells.length ? { status: "ok", data, env: raw, kind: firstKind(raw, layer!), fallback: true } : { status: "missing" };
    },
    { maxAgeMs: maxAgeMs(layer), keep: (a) => a.status === "ok" && savable(layer) },
  );
  if (live.idle) return { status: "idle" };
  if (live.phase === "error") return { status: "error", text: live.error ?? "" };
  if (!live.value) return { status: "loading" };
  return live.value.status === "ok" ? { ...live.value, live: { phase: live.phase, at: live.at } } : live.value;
}

/** Half side of the square asked around a position when falling back to the layer tool (covers the cell and its neighbours). */
const AROUND_M = 400;

/**
 * What it is like at one position: `mode` "air" gives every pollutant (citizen tool) or the one `layer` asked
 * (fallback); "emf" gives the electric field.
 */
export function useHereAnswer(mode: "air" | "emf", layer: string, position: { lon: number; lat: number } | null): Loaded<HereAnswer> {
  const { run } = useSession();
  // With the citizen tool one call covers every pollutant; the fallback is per layer.
  const tool: CitizenTool = mode === "air" ? "air_here" : "emf_here";
  const perLayer = missing.has(tool) ? `|${layer}` : "";
  const key = position ? `${mode}|${position.lon},${position.lat}${perLayer}` : null;
  return useLoaded<HereAnswer>(key, async () => {
    const p = position!;
    const env = await ask(run, tool, { point: [p.lon, p.lat] });
    if (env) {
      const data = mode === "air" ? parseAirHere(env.result) : parseEmfHere(env.result);
      if (data.readings.length) return { status: "ok", data, env, kind: firstKind(env), fallback: false };
    }
    const raw = (await run("query_layer", { layer, area: aroundPolygon(p.lon, p.lat, AROUND_M), limit: 200 })) as Envelope;
    if (!isOk(raw)) return { status: "missing" };
    const fine = normalizeLayer(raw.result);
    const cell = nearestCell(fine.items, p.lon, p.lat);
    if (!cell) return { status: "missing" };
    const kind = firstKind(raw, layer);
    const id = layer.replace(/^air_/, "");
    return {
      status: "ok",
      env: raw,
      kind,
      fallback: true,
      data: { readings: [{ id, label: metricInfo(layer).label, value: cell.value, low: cell.p5, high: cell.p95, unit: fine.unit, kind, references: [] }] },
    };
  });
}

/** Roadworks, closures, strikes and other transport events, plus how fresh each feed is. */
export interface TransportNow {
  events: TransportEvent[];
  feeds: FeedState[];
}

export function useTransportNow(time: string | null = null): Loaded<TransportNow> {
  const { run } = useSession();
  return useLoaded<TransportNow>(`now|${time ?? ""}`, async () => {
    const env = await ask(run, "transport_now", { area: "city", ...(time ? { time } : {}) });
    if (!env) return { status: "missing" };
    return { status: "ok", data: parseTransportNow(env.result), env, kind: firstKind(env), fallback: false };
  });
}

export interface PlacesQuery {
  kind: "sport" | "museum";
  /** ISO date and time the person wants to go. */
  at: string;
  sport?: string;
  point?: { lon: number; lat: number } | null;
  radiusM?: number;
}

/** Places for sport or culture and whether each is open at the chosen time. `query = null` waits. */
export interface PlacesOpen {
  places: OpenPlace[];
  coverage?: { withHours: number; total: number };
}

export function usePlacesOpen(query: PlacesQuery | null): Loaded<PlacesOpen> {
  const { run } = useSession();
  const key = query ? JSON.stringify(query) : null;
  return useLoaded<PlacesOpen>(key, async () => {
    const q = query!;
    const env = await ask(run, "places_open", {
      kind: q.kind,
      at: q.at,
      ...(q.sport ? { sport: q.sport } : {}),
      ...(q.point ? { point: [q.point.lon, q.point.lat], radius_m: q.radiusM ?? 3000 } : {}),
    });
    if (env) return { status: "ok", data: parsePlacesOpen(env.result), env, kind: firstKind(env), fallback: false };
    if (q.kind !== "sport") return { status: "missing" };
    // The facility register answers "where", not "when": every place comes back with hours unknown.
    const raw = (await run("sports_facilities", { area: "city", discipline: null })) as Envelope;
    const features = isOk(raw) && Array.isArray((raw.result as { features?: unknown[] }).features) ? (raw.result as { features: unknown[] }).features : null;
    if (!features) return { status: "missing" };
    const places = placesFromFacilities(features, { sport: q.sport, point: q.point, radiusM: q.radiusM ?? 3000 });
    return { status: "ok", data: { places, coverage: { withHours: 0, total: places.length } }, env: raw, kind: firstKind(raw), fallback: true };
  });
}
