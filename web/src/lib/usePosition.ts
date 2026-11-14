// The resident's chosen position ("here"), shared by every citizen screen so it is asked for once.
// It comes from the phone's GPS, from a tap on the map, or stays empty. It is kept only in this browser tab
// (sessionStorage) and is sent only as coordinates to the twin's tools: no account, no history.
import { useSyncExternalStore } from "react";
import { inRome } from "@/lib/here";

export interface Position {
  lon: number;
  lat: number;
  source: "gps" | "map";
}

/** "outside" = the device is not in Rome; "denied" = the person or the browser said no; "unavailable" = no GPS. */
export type LocateStatus = "idle" | "locating" | "denied" | "outside" | "unavailable";

const KEY = "urbs.position";

function load(): Position | null {
  try {
    const raw = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(KEY);
    const p = raw ? (JSON.parse(raw) as Partial<Position>) : null;
    return p && typeof p.lon === "number" && typeof p.lat === "number" && inRome(p.lon, p.lat)
      ? { lon: p.lon, lat: p.lat, source: p.source === "gps" ? "gps" : "map" }
      : null;
  } catch {
    return null;
  }
}

let state: { position: Position | null; status: LocateStatus } = { position: load(), status: "idle" };
const listeners = new Set<() => void>();

function update(next: Partial<typeof state>): void {
  state = { ...state, ...next };
  if ("position" in next) {
    try {
      if (state.position) sessionStorage.setItem(KEY, JSON.stringify(state.position));
      else sessionStorage.removeItem(KEY);
    } catch {
      // Private mode: the position simply is not remembered.
    }
  }
  for (const l of listeners) l();
}

export function setPosition(position: Position | null): void {
  update({ position, status: "idle" });
}

/** Asks the device where it is. Positions outside Rome are not used: the twin only knows Rome. */
export function locate(): void {
  if (typeof navigator === "undefined" || !navigator.geolocation) return update({ status: "unavailable" });
  update({ status: "locating" });
  navigator.geolocation.getCurrentPosition(
    (p) => {
      const { longitude: lon, latitude: lat } = p.coords;
      if (!inRome(lon, lat)) return update({ status: "outside" });
      // Rounded to about 10 m: precise enough for a 170 m cell, and no more than needed.
      update({ position: { lon: Math.round(lon * 1e4) / 1e4, lat: Math.round(lat * 1e4) / 1e4, source: "gps" }, status: "idle" });
    },
    (e) => update({ status: e.code === e.PERMISSION_DENIED ? "denied" : "unavailable" }),
    { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
  );
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => void listeners.delete(l);
};
const snapshot = () => state;

export function usePosition(): { position: Position | null; status: LocateStatus } {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
