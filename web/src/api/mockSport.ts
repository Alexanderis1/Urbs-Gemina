// Sample-data mode for the sports tools. Everything is synthetic and labelled "sample data".
import type { Envelope } from "./types";
import type { Coverage, SportFeature, ZoneRow } from "@/lib/sport";

export const SPORT_TOOLS = ["sports_facilities", "sport_coverage", "sport_deserts"] as const;
export type SportTool = (typeof SPORT_TOOLS)[number];

const NOW = "2026-11-13T12:00:00Z";
const WARN = "Sample data: the sports tools are not connected. Facilities, residents and coverage are placeholders.";
export const SAMPLE_DISCIPLINES = ["football", "tennis", "padel", "swimming", "basketball", "volleyball", "fitness", "athletics"];
const KINDS = ["sports_centre", "pool", "school_gym", "pitch", "gym"];

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function facilities(): SportFeature[] {
  const r = rng(42);
  return Array.from({ length: 60 }, (_, i) => {
    const lon = 12.38 + r() * 0.22;
    const lat = 41.83 + r() * 0.14;
    const kind = KINDS[Math.floor(r() * KINDS.length)]!;
    const ds = SAMPLE_DISCIPLINES.filter(() => r() < 0.3);
    const disciplines = ds.length ? ds : [SAMPLE_DISCIPLINES[i % SAMPLE_DISCIPLINES.length]!];
    const sample = (value: unknown) => ({ value, status: "open_data" as const, sources: [{ source: "ui_sample_data" }], label: "sample data" });
    const id = `sample_${String(i).padStart(3, "0")}`;
    return {
      type: "Feature",
      id,
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: {
        facility_id: id,
        name: `Sample ${kind.replace("_", " ")} ${i + 1}`,
        kind,
        municipio: String(1 + Math.floor(r() * 15)),
        disciplines,
        type: (["public", "school", "private", "unclassified"] as const)[Math.floor(r() * 4)]!,
        accessible: r() < 0.5 ? true : null,
        access: (["yes", "customers", "private", null] as const)[Math.floor(r() * 4)] ?? null,
        closed: r() < 0.05,
        fields: {
          hours: sample("Mon-Sat 9-21"),
          accessibility: r() < 0.5 ? sample("yes") : { value: null, status: "not_known", sources: [] },
          address: sample("Sample street"),
          contact: { value: null, status: "not_known", sources: [] },
        },
        discipline_details: Object.fromEntries(disciplines.map((d) => [d, sample(true)])),
        synthetic: false,
      },
    } satisfies SportFeature;
  });
}

const dist = (a: [number, number], b: [number, number]) => {
  const k = Math.cos((a[1] * Math.PI) / 180) * 111_320;
  return Math.hypot((a[0] - b[0]) * k, (a[1] - b[1]) * 111_320);
};

function coverage(discipline: string, extra: [number, number][]): Coverage {
  const reach = 615;
  const sites = facilities()
    .filter((f) => f.properties.disciplines.includes(discipline) && f.geometry)
    .map((f) => f.geometry!.coordinates)
    .concat(extra);
  const r = rng(7);
  const zones: ZoneRow[] = [];
  for (let zi = 0; zi < 12; zi++) {
    const c: [number, number] = [12.4 + (zi % 4) * 0.05, 41.85 + Math.floor(zi / 4) * 0.045];
    let res = 0, unc = 0, ch = 0, chu = 0;
    for (let p = 0; p < 25; p++) {
      const pt: [number, number] = [c[0] + (r() - 0.5) * 0.04, c[1] + (r() - 0.5) * 0.035];
      const people = Math.round(150 + r() * 250);
      const kids = Math.round(people * 0.15);
      res += people;
      ch += kids;
      if (!sites.some((s) => dist(s, pt) <= reach)) {
        unc += people;
        chu += kids;
      }
    }
    const share = Math.round((unc / res) * 10000) / 10000;
    zones.push({ zone: `S${zi + 1}`, residents: res, children: ch, residents_uncovered: unc, children_uncovered: chu, uncovered_share: share, desert: share >= 0.5 && res >= 1000, centroid: c });
  }
  const sum = (k: keyof ZoneRow) => zones.reduce((a, z) => a + (z[k] as number), 0);
  return {
    discipline,
    reach_m: reach,
    facilities_offering: sites.length,
    residents_total: sum("residents"),
    residents_uncovered: sum("residents_uncovered"),
    children_total: sum("children"),
    children_uncovered: sum("children_uncovered"),
    zones,
    desert_zones: zones.filter((z) => z.desert).map((z) => z.zone),
  };
}

async function sha(text: string) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");
}

export async function mockSportTool(tool: SportTool, inputs: Record<string, unknown>): Promise<Envelope> {
  const gyms = inputs.open_school_gyms ?? inputs.open_facilities;
  const whatIf = Array.isArray(gyms) && gyms.length > 0;
  let result: Record<string, unknown>;
  if (tool === "sports_facilities") {
    const fs = facilities().filter((f) => !inputs.discipline || f.properties.disciplines.includes(String(inputs.discipline)));
    result = { type: "FeatureCollection", count: fs.length, features: fs };
  } else {
    const d = String(inputs.discipline ?? "football");
    const open = whatIf ? (gyms as { lon: number; lat: number }[]) : [];
    const base = coverage(d, []);
    if (open.length) {
      const variant = coverage(d, open.map((o) => [o.lon, o.lat] as [number, number]));
      result = {
        baseline: base,
        variant,
        added: open.map((_, i) => `sim_${i}`),
        delta: {
          residents_newly_covered: base.residents_uncovered - variant.residents_uncovered,
          children_newly_covered: base.children_uncovered - variant.children_uncovered,
        },
      };
    } else result = { ...base };
  }
  return {
    run_id: await sha(`${tool}|${JSON.stringify(inputs)}|sample-v2`),
    tool,
    inputs,
    result,
    data_kinds: whatIf
      ? { facilities: "real", population: "real", reach: "estimated", what_if: "simulated" }
      : tool === "sports_facilities"
        ? { facilities: "real" }
        : { facilities: "real", population: "real", reach: "estimated" },
    sources: [{ id: "ui_sample_data", retrieved_at: NOW }],
    synthetic: whatIf,
    warnings: [WARN],
  };
}
