// Change objects for run_scenario, in the shapes WS4 publishes (twin/scenarios).
// Note: add_antennas is estimate_field's variant shape, not run_scenario's.
export type ScenarioKind = "antenna" | "population_exposure" | "road_closure";

export const SCENARIO_BANDS = ["800", "900", "1800", "2100", "3500"] as const;

function site(f: Record<string, string>): Record<string, unknown> {
  return {
    lon: Number(f.lon),
    lat: Number(f.lat),
    ...(f.height_m?.trim() ? { height_m: Number(f.height_m) } : {}),
    band: f.band ?? "3500",
  };
}

export function buildScenarioChange(kind: ScenarioKind, f: Record<string, string>): Record<string, unknown> {
  if (kind === "antenna") return { action: "add", site: site(f) };
  if (kind === "population_exposure") return { site: site(f) };
  return { close: { street: (f.street ?? "").trim() } };
}
