// Map actions: the same five client tools for chat (TwinAnswer.map_actions) and voice
// (ElevenLabs clientTools). Names and arguments follow voice/client_tools.json (shared interface 8).
// Anything malformed, unknown, or pointing outside Rome is dropped.
import type { Area } from "./area";

/** Roma Capitale bounding box, copied from config/areas.yaml (city.bbox): [minLon, minLat, maxLon, maxLat]. */
export const ROME_BBOX = [12.234, 41.655, 12.856, 42.141] as const;

export const SCREENS = ["city", "ask", "permit", "scenario", "honesty"] as const;
export type ActionScreen = (typeof SCREENS)[number];

export type MapAction =
  | { tool: "fly_to"; args: { lon: number; lat: number; zoom?: number; label?: string } }
  | { tool: "show_area"; args: { area: string } }
  | { tool: "show_layer"; args: { layer: string; visible: boolean } }
  | { tool: "show_radius"; args: { lon: number; lat: number; radius_m: number; run_id?: string } }
  | { tool: "open_screen"; args: { screen: ActionScreen } };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isStr = (v: unknown): v is string => typeof v === "string" && v.length > 0;

export function inRome(lon: number, lat: number): boolean {
  return lon >= ROME_BBOX[0] && lat >= ROME_BBOX[1] && lon <= ROME_BBOX[2] && lat <= ROME_BBOX[3];
}

export function parseMapAction(raw: unknown): MapAction | null {
  if (!isObj(raw) || !isStr(raw.tool) || !isObj(raw.args)) return null;
  const a = raw.args;
  switch (raw.tool) {
    case "fly_to": {
      if (!isNum(a.lon) || !isNum(a.lat) || !inRome(a.lon, a.lat)) return null;
      const args: { lon: number; lat: number; zoom?: number; label?: string } = { lon: a.lon, lat: a.lat };
      if (isNum(a.zoom)) args.zoom = a.zoom;
      if (isStr(a.label)) args.label = a.label;
      return { tool: "fly_to", args };
    }
    case "show_area":
      return isStr(a.area) && areaFromId(a.area) ? { tool: "show_area", args: { area: a.area } } : null;
    case "show_layer":
      return isStr(a.layer) && typeof a.visible === "boolean"
        ? { tool: "show_layer", args: { layer: a.layer, visible: a.visible } }
        : null;
    case "show_radius": {
      if (!isNum(a.lon) || !isNum(a.lat) || !isNum(a.radius_m) || a.radius_m <= 0 || !inRome(a.lon, a.lat)) return null;
      const args: { lon: number; lat: number; radius_m: number; run_id?: string } = { lon: a.lon, lat: a.lat, radius_m: a.radius_m };
      if (isStr(a.run_id)) args.run_id = a.run_id;
      return { tool: "show_radius", args };
    }
    case "open_screen":
      return SCREENS.includes(a.screen as ActionScreen) ? { tool: "open_screen", args: { screen: a.screen as ActionScreen } } : null;
    default:
      return null;
  }
}

export function parseMapActions(raw: unknown): MapAction[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseMapAction).filter((a): a is MapAction => a !== null);
}

/** "city" | "municipio:<id>" | "zone:<id>" -> Area. */
export function areaFromId(id: string): Area | null {
  if (id === "city") return { type: "city" };
  const m = /^(municipio|zone):(.+)$/.exec(id);
  if (!m) return null;
  return m[1] === "municipio" ? { type: "municipio", id: m[2]! } : { type: "zone", id: m[2]! };
}
