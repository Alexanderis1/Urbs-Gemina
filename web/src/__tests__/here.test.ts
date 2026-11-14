import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import {
  aroundPolygon,
  cellSpacingM,
  coarseCells,
  inRome,
  nearestCell,
  parseAirHere,
  parseCityHeatmap,
  parseEmfHere,
  parsePlacesOpen,
  parseTransportNow,
  placesFromFacilities,
  referenceLabel,
  shareBelow,
} from "@/lib/here";

const cell = (lat: number, lon: number) => latLngToCell(lat, lon, 9);

describe("the resident's own position", () => {
  it("knows whether a position is inside Rome", () => {
    expect(inRome(12.4769, 41.8986)).toBe(true);
    expect(inRome(9.19, 45.46)).toBe(false);
  });

  it("draws a small closed square around a position, for asking the layer tools", () => {
    const p = aroundPolygon(12.48, 41.9, 500);
    const ring = p.coordinates[0]!;
    expect(p.type).toBe("Polygon");
    expect(ring).toHaveLength(5);
    expect(ring[0]).toEqual(ring[4]);
    // About 1 km wide: 500 m each side of the point.
    const widthDeg = ring[1]![0]! - ring[0]![0]!;
    expect(widthDeg * 111_320 * Math.cos((41.9 * Math.PI) / 180)).toBeCloseTo(1000, -1);
  });

  it("picks the cell the position is in", () => {
    const items = [
      { h3: cell(41.9, 12.48), value: 30, uncertainty: 2 },
      { h3: cell(41.95, 12.6), value: 10, uncertainty: 1 },
    ];
    expect(nearestCell(items, 12.4801, 41.9001)?.value).toBe(30);
    expect(nearestCell([], 12.48, 41.9)).toBeNull();
  });

  it("says how a value compares with the rest of the city right now", () => {
    expect(shareBelow([10, 20, 30, 40], 35)).toBe(75);
    expect(shareBelow([], 5)).toBeNull();
  });
});

describe("the whole city as a heatmap", () => {
  it("merges fine cells into larger ones by averaging, so a thinned city sample has no holes", () => {
    const a = cell(41.9, 12.48);
    const out = coarseCells(
      [
        { h3: a, value: 10, p5: 8, p95: 12 },
        { h3: a, value: 30, p5: 20, p95: 40 },
      ],
      7,
    );
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ value: 20, low: 8, high: 40 });
    // The merged cell keeps its hexagon, so the map can draw it as one clean tile.
    expect(out[0]!.h3).toMatch(/^87/);
    expect(out[0]!.lon).toBeCloseTo(12.48, 1);
  });

  it("measures how far apart the cells are, to size the patches on the map", () => {
    const cells = [
      { lon: 12.4, lat: 41.9, value: 1 },
      { lon: 12.4, lat: 41.91, value: 1 },
      { lon: 12.5, lat: 41.9, value: 1 },
    ];
    expect(cellSpacingM(cells)).toBeCloseTo(1113, -2);
    expect(cellSpacingM([cells[0]!])).toBeNull();
  });

  it("reads the city_heatmap tool", () => {
    const h = parseCityHeatmap({
      cells: [{ lon: 12.4, lat: 41.9, value: 22, low: 18, high: 30, level: 2 }, { lon: "x" }],
      legend: [{ index: 2, label_it: "Discreta", label_en: "Fair", from: 20, to: 40 }],
      unit: "ug/m3",
    });
    expect(h.cells).toEqual([{ lon: 12.4, lat: 41.9, value: 22, low: 18, high: 30, level: 2 }]);
    expect(h.legend).toEqual([{ index: 2, label: "Fair", from: 20, to: 40 }]);
    expect(h.unit).toBe("µg/m³");
  });

  it("keeps the twin's own cell of each patch and takes the unit from the legend", () => {
    const id = latLngToCell(41.9, 12.48, 8);
    const h = parseCityHeatmap({
      cells: [{ cell: id, lon: 12.48, lat: 41.9, value: 31, low: 25, high: 40, level: 3 }],
      legend: [{ index: 3, label_it: "Moderata", from: 25, to: 60, unit: "µg/m³" }],
    });
    expect(h.cells[0]!.h3).toBe(id);
    expect(h.unit).toBe("µg/m³");
  });

  it("orders the traffic bands from free flowing to blocked, like every other scale (higher = worse)", () => {
    const h = parseCityHeatmap({
      layer: "road_speed",
      cells: [{ lon: 12.48, lat: 41.9, value: 12, level: 1 }],
      legend: [
        { index: 1, label_it: "Bloccato", from: 0, to: 0.4, unit: "velocità / velocità libera" },
        { index: 2, label_it: "Congestionato", from: 0.4, to: 0.6 },
        { index: 3, label_it: "Rallentato", from: 0.6, to: 0.8 },
        { index: 4, label_it: "Scorrevole", from: 0.8, to: null },
      ],
    });
    expect(h.legend.map((b) => [b.index, b.label])).toEqual([[1, "Scorrevole"], [2, "Rallentato"], [3, "Congestionato"], [4, "Bloccato"]]);
    expect(h.cells[0]!.level).toBe(4);
    // The bands are shares of the free-flow speed: that is not the unit of the speed values.
    expect(h.unit).toBe("");
  });

  it("names a reference value in plain words", () => {
    expect(referenceLabel("no2_hourly_limit")).toBe("Hourly limit");
    expect(referenceLabel("pm25_annual_limit")).toBe("Yearly limit");
    expect(referenceLabel("o3_target_8h")).toBe("Target value (8 hours)");
    expect(referenceLabel("attention_value")).toBe("Attention value");
    expect(referenceLabel("Limite annuale")).toBe("Limite annuale");
  });
});

describe("answers of the citizen tools", () => {
  it("reads air_here: each pollutant with its range, its level in words and the reference values", () => {
    const a = parseAirHere({
      summary_it: "Aria buona.",
      summary_en: "The air is good.",
      pollutants: [
        {
          id: "no2",
          label: "NO₂",
          value: 21.4,
          low: 15,
          high: 30,
          unit: "ug/m3",
          kind: "estimated",
          level: { index: 1, label_it: "Buona", label_en: "Good" },
          references: [{ name: "Annual limit", value: 40, averaging: "year", source: "D.Lgs. 155/2010" }],
        },
      ],
    });
    expect(a.summary).toBe("The air is good.");
    expect(a.readings[0]).toMatchObject({ id: "no2", label: "NO₂", value: 21.4, low: 15, high: 30, unit: "µg/m³", kind: "estimated", level: { index: 1, label: "Good" } });
    expect(a.readings[0]!.references[0]).toMatchObject({ name: "Annual limit", value: 40 });
  });

  it("reads emf_here as one reading", () => {
    const e = parseEmfHere({ value: 0.8, low: 0.4, high: 1.5, unit: "V/m", kind: "estimated", level: { index: 1, label_it: "Basso" }, references: [], summary_it: "Ok." });
    expect(e.readings).toHaveLength(1);
    expect(e.readings[0]).toMatchObject({ id: "emf", value: 0.8, unit: "V/m", level: { index: 1, label: "Basso" } });
    expect(e.summary).toBe("Ok.");
  });

  it("reads transport_now: events (with or without a position) and how fresh each feed is", () => {
    const t = parseTransportNow({
      events: [
        { title: "Lavori in via Appia", category: "lavori", start: "2026-11-14T06:00:00Z", end: null, source: "Roma Mobilità", description: "Corsia chiusa", lines: ["85"], lon: 12.5, lat: 41.87 },
        { title: "Sciopero", category: "sciopero", lon: null, lat: null },
      ],
      feeds: [{ id: "gtfs_rt", last_update: "2026-11-13T18:25:00Z", stale: true }],
    });
    expect(t.events).toHaveLength(2);
    expect(t.events[0]).toMatchObject({ title: "Lavori in via Appia", category: "lavori", position: [12.5, 41.87], lines: ["85"] });
    expect(t.events[1]!.position).toBeUndefined();
    expect(t.feeds[0]).toMatchObject({ id: "gtfs_rt", stale: true });
  });

  it("reads the street and the category in words of a transport notice", () => {
    const t = parseTransportNow({
      events: [{ id: "alert-7", title: "Corteo in centro", category: "evento", category_label: "Evento", street: "Via Cavour", lines: [], lon: 12.49, lat: 41.89 }],
    });
    expect(t.events[0]).toMatchObject({ id: "alert-7", category: "evento", categoryLabel: "Evento", street: "Via Cavour" });
  });

  it("reads places_open: open, closed or hours unknown", () => {
    const p = parsePlacesOpen({
      places: [
        { name: "Musei Capitolini", address: "Piazza del Campidoglio 1", category: "museum", opening_hours: "09:30-19:30", open_at: true, source: "OSM", lon: 12.48, lat: 41.89 },
        { name: "Campo", open_at: null, lon: 12.5, lat: 41.9 },
        { name: "No position" },
      ],
      coverage: { with_hours: 1, total: 2 },
    });
    expect(p.places).toHaveLength(2);
    expect(p.places[0]).toMatchObject({ name: "Musei Capitolini", open: true, hours: "09:30-19:30", position: [12.48, 41.89] });
    expect(p.places[1]!.open).toBeNull();
    expect(p.coverage).toEqual({ withHours: 1, total: 2 });
  });

  it("reads the extras of a place: distance, ticket, step-free access, web site, sports", () => {
    const p = parsePlacesOpen({
      places: [
        { name: "MAXXI", open_at: null, distance_m: 812, fee: "yes", wheelchair: "limited", website: "https://www.maxxi.art", lon: 12.46, lat: 41.93 },
        { name: "Piscina", open_at: true, disciplines: ["swimming"], hours_note: "dichiarati dal gestore", lon: 12.5, lat: 41.9 },
      ],
    });
    expect(p.places[0]).toMatchObject({ distanceM: 812, fee: "yes", wheelchair: "limited", website: "https://www.maxxi.art" });
    expect(p.places[1]).toMatchObject({ disciplines: ["swimming"], hoursNote: "dichiarati dal gestore" });
  });
});

describe("sport places when the opening-hours tool is not there", () => {
  const facility = (name: string | null, disciplines: string[], lon: number, lat: number, closed = false) => ({
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { name, kind: "pitch", disciplines, closed },
  });
  const all = [
    facility("Campo Testaccio", ["soccer"], 12.476, 41.876),
    facility("Piscina", ["swimming"], 12.48, 41.9),
    facility(null, ["calcio"], 12.49, 41.9),
    facility("Lontano", ["soccer"], 12.7, 42.05),
    facility("Chiuso", ["soccer"], 12.48, 41.9, true),
  ];

  it("keeps the facilities for the chosen sport, in Italian or as the register writes it", () => {
    const out = placesFromFacilities(all, { sport: "calcio" });
    expect(out.map((p) => p.name)).toEqual(["Campo Testaccio", "Calcio", "Lontano", "Chiuso"]);
  });

  it("never says a place is open without opening hours: unknown, or closed when the register says so", () => {
    const out = placesFromFacilities(all, {});
    expect(out.find((p) => p.name === "Piscina")!.open).toBeNull();
    expect(out.find((p) => p.name === "Chiuso")!.open).toBe(false);
  });

  it("with a point, keeps only what is within the radius, nearest first", () => {
    const out = placesFromFacilities(all, { sport: "calcio", point: { lon: 12.48, lat: 41.9 }, radiusM: 3000 });
    expect(out.map((p) => p.name)).toEqual(["Chiuso", "Calcio", "Campo Testaccio"]);
  });
});
