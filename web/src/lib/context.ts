// Reads the live context_check result: groups -> layers -> hits.
export interface ContextHit {
  group: string;
  groupLabel: string;
  layer: string;
  layerLabel: string;
  name: string;
  distance_m: number;
}

export interface ContextLayer {
  layer: string;
  label: string;
  status: string;
  count?: number;
  hits?: { distance_m: number; name: string | null }[];
}

export interface ContextGroup {
  label: string;
  layers: ContextLayer[];
}

export interface ContextResult {
  point: { lon: number; lat: number };
  radius_m: number;
  meaning: string;
  groups: Record<string, ContextGroup>;
}

export function contextRows(result: unknown): ContextHit[] {
  const r = result as ContextResult;
  const rows: ContextHit[] = [];
  for (const [group, g] of Object.entries(r.groups ?? {}))
    for (const l of g.layers)
      for (const h of l.hits ?? [])
        rows.push({ group, groupLabel: g.label, layer: l.layer, layerLabel: l.label, name: h.name ?? "(unnamed)", distance_m: h.distance_m });
  return rows.sort((a, b) => a.distance_m - b.distance_m);
}

export function contextSummary(result: unknown) {
  const r = result as ContextResult;
  let notAvailable = 0;
  let sensitiveHits = 0;
  const unavailable: string[] = [];
  for (const [group, g] of Object.entries(r.groups ?? {}))
    for (const l of g.layers) {
      if (l.status !== "ok") {
        notAvailable++;
        unavailable.push(l.label);
      }
      if (group === "sensitive_site") sensitiveHits += l.count ?? 0;
    }
  return { notAvailable, sensitiveHits, unavailable };
}
