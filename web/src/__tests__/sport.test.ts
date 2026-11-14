import { describe, expect, it } from "vitest";
import { fieldLabel, filterFacilities, buildManagerUpdate, typeLabel, accessLabel, type SportFeature } from "@/lib/sport";
import { setLang } from "@/lib/i18n";
import { mockSportTool } from "@/api/mockSport";
import { parseEnvelope } from "@/api/envelope";

const f = (over: Partial<SportFeature["properties"]> = {}): SportFeature => ({
  type: "Feature",
  id: "f1",
  geometry: { type: "Point", coordinates: [12.5, 41.9] },
  properties: {
    facility_id: "f1",
    name: "Centro sportivo",
    kind: "sports_centre",
    municipio: "1",
    disciplines: ["football", "tennis"],
    type: "public",
    accessible: true,
    fields: { accessibility: { value: "yes", status: "official", sources: [] } },
    discipline_details: {},
    synthetic: false,
    ...over,
  },
});

describe("sport screen helpers", () => {
  it("shows the label next to a web value", () => {
    expect(fieldLabel({ value: "9-21", status: "web_unverified", sources: [], label: "from the web, unverified" })).toBe(
      "from the web, unverified",
    );
  });
  it("names the status when no label is given", () => {
    expect(fieldLabel({ value: null, status: "not_known", sources: [] })).toBe("not known");
    expect(fieldLabel({ value: "x", status: "manager_confirmed", sources: [] })).toBe("confirmed by manager");
  });
  it("filters by discipline, kind, municipio and accessibility", () => {
    const list = [f(), f({ facility_id: "f2", kind: "pool", disciplines: ["swimming"], municipio: "2", type: "unclassified", accessible: null })];
    expect(filterFacilities(list, { discipline: "tennis" }).map((x) => x.properties.facility_id)).toEqual(["f1"]);
    expect(filterFacilities(list, { kind: "pool" })).toHaveLength(1);
    expect(filterFacilities(list, { municipio: "2" })).toHaveLength(1);
    expect(filterFacilities(list, { accessibleOnly: true })).toHaveLength(1);
    expect(filterFacilities(list, { type: "public" })).toHaveLength(1);
  });
  it("builds a manager update from an organisational account only", () => {
    const u = buildManagerUpdate("f1", "hours", "Mon-Fri 9-21", "org:asd-roma", "2026-11-13T20:00:00Z");
    expect(u).toEqual({ facility_id: "f1", field: "hours", value: "Mon-Fri 9-21", account_ref: "org:asd-roma", confirmed_at: "2026-11-13T20:00:00Z" });
    expect(() => buildManagerUpdate("f1", "hours", "x", "Mario Rossi", "t")).toThrow(/organisational/);
    expect(() => buildManagerUpdate("f1", "municipio", "x", "org:a", "t")).toThrow(/cannot be edited/);
  });
});

describe("sport tools in sample mode", () => {
  it("sports_facilities returns a FeatureCollection that is not simulated", async () => {
    const env = parseEnvelope(await mockSportTool("sports_facilities", { area: "city", discipline: null }));
    expect(env.synthetic).toBe(false);
    expect(env.warnings.join(" ")).toMatch(/sample data/i);
    const r = env.result as { type: string; features: SportFeature[] };
    expect(r.type).toBe("FeatureCollection");
    expect(r.features.length).toBeGreaterThan(5);
    expect(r.features.some((x) => x.properties.synthetic)).toBe(false);
  });
  it("sport_deserts what-if returns baseline, variant and delta", async () => {
    const env = await mockSportTool("sport_coverage", {
      area: "municipio:1",
      discipline: "football",
      open_school_gyms: [{ name: "Scuola", lon: 12.49, lat: 41.9 }],
    });
    expect(env.synthetic).toBe(true);
    expect(env.data_kinds.what_if).toBe("simulated");
    const r = env.result as { baseline: unknown; variant: unknown; delta: { residents_newly_covered: number } };
    expect(r.baseline).toBeDefined();
    expect(r.variant).toBeDefined();
    expect(r.delta.residents_newly_covered).toBeGreaterThanOrEqual(0);
  });
});

describe("facility type", () => {
  it("says type not known for unclassified", async () => {
    const { typeLabel } = await import("@/lib/sport");
    expect(typeLabel("unclassified")).toBe("type not known");
    expect(typeLabel("school")).toBe("school");
  });
});

describe("facility names", () => {
  it("falls back to kind plus address when the name is empty", async () => {
    const { displayName } = await import("@/lib/sport");
    const x = f({ name: "", kind: "school_gym", fields: { address: { value: "Via Appia 10", status: "official", sources: [] } } });
    expect(displayName(x)).toBe("school gym, Via Appia 10");
    expect(displayName(f())).toBe("Centro sportivo");
  });
});

describe("access and closed facilities", () => {
  it("says access not known when the source has none", async () => {
    const { accessLabel } = await import("@/lib/sport");
    expect(accessLabel(null)).toBe("access not known");
    expect(accessLabel(undefined)).toBe("access not known");
    expect(accessLabel("customers")).toBe("customers only");
    expect(accessLabel("yes")).toBe("open to the public");
    expect(accessLabel("private")).toBe("private");
  });

  it("treats closed, private and no-access facilities as inactive", async () => {
    const { isInactive } = await import("@/lib/sport");
    expect(isInactive(f({ closed: true }))).toBe(true);
    expect(isInactive(f({ access: "private" }))).toBe(true);
    expect(isInactive(f({ access: "no" }))).toBe(true);
    expect(isInactive(f({ access: "customers" }))).toBe(false);
    expect(isInactive(f({ access: null }))).toBe(false);
    expect(isInactive(f())).toBe(false);
  });

  it("groups many facilities into hexagons with active and inactive counts", async () => {
    const { clusterH3 } = await import("@/lib/sport");
    const list = [
      f({ facility_id: "a" }),
      f({ facility_id: "b", closed: true }),
      { ...f({ facility_id: "c" }), geometry: { type: "Point" as const, coordinates: [12.6, 41.8] as [number, number] } },
      { ...f({ facility_id: "d" }), geometry: null },
    ];
    const cells = clusterH3(list, 8);
    expect(cells).toHaveLength(2);
    const total = cells.reduce((s, c) => s + c.count, 0);
    expect(total).toBe(3);
    const first = cells.find((c) => c.count === 2)!;
    expect(first.active).toBe(1);
    expect(typeof first.h3).toBe("string");
  });

  it("only clusters when zoomed out and the list is large", async () => {
    const { shouldCluster } = await import("@/lib/sport");
    expect(shouldCluster(14062, 11.5)).toBe(true);
    expect(shouldCluster(14062, 14)).toBe(false);
    expect(shouldCluster(300, 11)).toBe(false);
  });
});

describe("sport in Italian", () => {
  it("speaks Italian", () => {
    setLang("it");
    try {
      expect(fieldLabel({ value: 1, status: "manager_confirmed", sources: [] })).toBe("confermato dal gestore");
      expect(typeLabel("school")).toBe("scolastico");
      expect(accessLabel("customers")).toBe("solo clienti");
      expect(accessLabel(null)).toBe("accesso non noto");
    } finally {
      setLang("en");
    }
  });
});
