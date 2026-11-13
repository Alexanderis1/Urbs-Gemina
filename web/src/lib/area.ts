import type { PolygonGeometry } from "@/api/types";

// Shared interface 2: `area` = "city", a municipio id, an urban-zone id, or a GeoJSON polygon.
// Ids fixed by the hub: "city", "municipio:<1..15>", "zone:<CODE>" (DIPDIT:ZoneUrbanistiche code, upper case),
// or a GeoJSON Polygon (drawn area or the 300 m circle).
export type Area =
  | { type: "city" }
  | { type: "municipio"; id: string }
  | { type: "zone"; id: string; name?: string }
  | { type: "polygon"; geometry: PolygonGeometry };

export type AreaArg = string | PolygonGeometry;

export function areaToArg(a: Area): AreaArg {
  switch (a.type) {
    case "city":
      return "city";
    case "municipio":
      return `municipio:${a.id}`;
    case "zone":
      return `zone:${a.id.toUpperCase()}`;
    case "polygon":
      return a.geometry;
  }
}

export function areaLabel(a: Area): string {
  switch (a.type) {
    case "city":
      return "Whole city";
    case "municipio":
      return `Municipio ${roman(Number(a.id))}`;
    case "zone":
      return a.name ? `Zone ${a.id} ${a.name}` : `Zone ${a.id}`;
    case "polygon":
      return "Drawn area";
  }
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"];

/** Municipi are numbered 1..15 in ids and shown in Roman numerals, as Roma Capitale does. */
export function roman(n: number): string {
  return ROMAN[n] ?? String(n);
}

export const MUNICIPI = Array.from({ length: 15 }, (_, i) => String(i + 1));
