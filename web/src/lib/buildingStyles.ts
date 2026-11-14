// Colour expressions for the G0 building tiles (WS2 attributes, 13 Nov 2026).
// height_sd_m: height uncertainty (m). vertical_mm_yr: InSAR ground motion (negative = sinking), estimated.
// roof_material: centre district only, estimated.
import type { ExpressionSpecification } from "maplibre-gl";
import { MAP_PALETTE, type Theme } from "./theme";

export type BuildingView = "plain" | "height_sd" | "insar" | "roof";

export const BUILDING_VIEWS: { id: BuildingView; label: string; kind: "real" | "estimated" }[] = [
  { id: "plain", label: "Plain", kind: "estimated" },
  { id: "height_sd", label: "Height uncertainty", kind: "estimated" },
  { id: "insar", label: "Ground motion (InSAR)", kind: "estimated" },
  { id: "roof", label: "Roof material", kind: "estimated" },
];

export const ROOF_COLORS: Record<string, string> = {
  clay_tiles: "#c2410c",
  flat_light: "#e7e5e4",
  mixed: "#a8a29e",
  green_roof: "#4d7c0f",
  dark_or_shaded: "#44403c",
  unknown: "#d6d3d1",
};

export function buildingColor(view: BuildingView, theme: Theme = "light"): ExpressionSpecification | string {
  const p = MAP_PALETTE[theme];
  switch (view) {
    case "plain":
      // Measured heights a touch stronger than estimated ones.
      return ["match", ["get", "data_kind"], "real", p.building, p.buildingEstimated];
    case "height_sd":
      // 0 m (sure) -> pale, 6 m or more -> deep purple. No value = grey.
      return [
        "case",
        ["has", "height_sd_m"],
        ["interpolate", ["linear"], ["get", "height_sd_m"], 0, "#f5f3ff", 2, "#c4b5fd", 4, "#8b5cf6", 6, "#4c1d95"],
        "#d6d3d1",
      ];
    case "insar":
      // Sinking (negative) red, stable grey, rising blue. mm per year.
      return [
        "case",
        ["has", "vertical_mm_yr"],
        ["interpolate", ["linear"], ["get", "vertical_mm_yr"], -10, "#b91c1c", -3, "#fca5a5", 0, "#e7e5e4", 3, "#93c5fd", 10, "#1d4ed8"],
        "#f5f5f4",
      ];
    case "roof":
      return ["match", ["coalesce", ["get", "roof_material"], "unknown"], ...Object.entries(ROOF_COLORS).flat(), "#d6d3d1"] as unknown as ExpressionSpecification;
  }
}

export const LEGENDS: Record<Exclude<BuildingView, "plain" | "roof">, { gradient: string; low: string; high: string }> = {
  height_sd: { gradient: "linear-gradient(90deg,#f5f3ff,#c4b5fd,#8b5cf6,#4c1d95)", low: "0 m (sure)", high: "6 m+ (unsure)" },
  insar: { gradient: "linear-gradient(90deg,#b91c1c,#fca5a5,#e7e5e4,#93c5fd,#1d4ed8)", low: "−10 mm/yr sinking", high: "+10 rising" },
};
