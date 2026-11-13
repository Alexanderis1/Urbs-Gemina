import type { PolygonGeometry } from "@/api/types";

// Shared interface 2: `area` = "city", a municipio id, an urban-zone id, or a GeoJSON polygon.
// The "municipio:<id>" / "zone:<id>" prefixes are provisional until WS4 publishes the schema.
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
      return `zone:${a.id}`;
    case "polygon":
      return a.geometry;
  }
}

export function areaLabel(a: Area): string {
  switch (a.type) {
    case "city":
      return "Whole city";
    case "municipio":
      return `Municipio ${a.id}`;
    case "zone":
      return a.name ? `Zone ${a.id} ${a.name}` : `Zone ${a.id}`;
    case "polygon":
      return "Drawn area";
  }
}

/** Rome's 15 municipi, by their official Roman-numeral ids. Geometry comes from the WFS layer at runtime. */
export const MUNICIPI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"];
