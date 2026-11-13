// Event bus that carries map actions to the City view.
// Sources: TwinAnswer.map_actions from the Ask screen, and the ElevenLabs voice widget's client tools
// (register one handler per tool name that calls window.urbsMap.dispatch({ tool, args })).
// If no City view is on screen, map actions are queued, the app switches to City view, and the
// City view replays them when it mounts.
import { parseMapAction, type MapAction } from "./mapActions";

export const MAP_EVENT = "urbs:map";

let cityViews = 0;
let pending: MapAction[] = [];

export const needsCityView = (a: MapAction) => a.tool !== "open_screen" && cityViews === 0;

/** Validates and broadcasts one action. Returns false if it was dropped. */
export function dispatchMapAction(raw: unknown): boolean {
  const action = parseMapAction(raw);
  if (!action) return false;
  if (needsCityView(action)) pending.push(action);
  window.dispatchEvent(new CustomEvent<MapAction>(MAP_EVENT, { detail: action }));
  return true;
}

export function onMapAction(fn: (a: MapAction) => void): () => void {
  const h = (e: Event) => fn((e as CustomEvent<MapAction>).detail);
  window.addEventListener(MAP_EVENT, h);
  return () => window.removeEventListener(MAP_EVENT, h);
}

/** Called by the City view after its listeners are registered. Replays queued actions. */
export function registerCityView(): () => void {
  cityViews++;
  const queued = pending;
  pending = [];
  for (const a of queued) window.dispatchEvent(new CustomEvent<MapAction>(MAP_EVENT, { detail: a }));
  return () => {
    cityViews--;
  };
}

declare global {
  interface Window {
    /** Hook for the voice widget and for manual testing in the browser console. */
    urbsMap?: { dispatch: (raw: unknown) => boolean };
  }
}
if (typeof window !== "undefined") window.urbsMap = { dispatch: dispatchMapAction };
