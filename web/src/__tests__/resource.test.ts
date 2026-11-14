import { describe, expect, it } from "vitest";
import { setLang } from "@/lib/i18n";
import { normalizeLayer } from "@/lib/layers";
import { describeResource } from "@/lib/resource";

const hospital = {
  type: "features",
  count: 1,
  features: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "Ospedali.7",
        geometry: { type: "Point", coordinates: [12.4485, 41.9084] },
        properties: { DESCRIZION: "Oftalmico", INDIRIZZO: "P.le degli Eroi", OSP_NUMCIV: "11", OSP_NLETTI: 300, OSP_X: 2308389, OSP_CODICE: 8, telefono: "06 000" },
      },
    ],
  },
};

const station = {
  type: "observations",
  observations: [
    {
      id: "urn:ngsi-ld:AirQualityObserved:eea-IT1836A",
      lon: 12.4476,
      lat: 41.9064,
      observed_at: "2026-11-14T05:00:00+00:00",
      values: { no2: 11.0, pm10: 20.5 },
      sigma: { no2: 1.65, pm10: 0 },
      synthetic: false,
    },
  ],
};

const loop = {
  type: "observations",
  observations: [{ id: "urn:ngsi-ld:TrafficFlowObserved:sim-loop-009", lon: 12.44, lat: 41.9, values: { intensity: 893.4 }, sigma: { intensity: 71.5 }, synthetic: true }],
};

describe("what the click card says about one thing on the map", () => {
  it("names a place and lists the facts a person can use, in plain labels", () => {
    const data = normalizeLayer(hospital);
    const r = describeResource(data.items[0]!, data, "hospitals");
    expect(r.title).toBe("Oftalmico");
    expect(r.category).toBe("Hospital");
    expect(r.glyph).toBe("hospital");
    expect(r.facts).toContainEqual({ label: "Address", value: "P.le degli Eroi 11" });
    expect(r.facts).toContainEqual({ label: "Beds", value: "300" });
    expect(r.position).toEqual([12.4485, 41.9084]);
    expect(r.main).toBeUndefined();
  });

  it("never shows contact details, and keeps technical fields for staff only", () => {
    const data = normalizeLayer(hospital);
    const r = describeResource(data.items[0]!, data, "hospitals");
    const all = JSON.stringify(r);
    expect(all).not.toContain("06 000");
    expect(r.facts.map((f) => f.label)).not.toContain("OSP_X");
    expect(r.extra).toEqual([{ label: "OSP_CODICE", value: "8" }]);
  });

  it("gives a sensor its main reading, every other reading, and when it was taken", () => {
    const data = normalizeLayer(station);
    const r = describeResource(data.items[0]!, data, "air_quality");
    expect(r.title).toBe("Air quality station IT1836A");
    expect(r.glyph).toBe("air");
    // The map is coloured by PM10 when a station reports it, so that reading comes first.
    expect(r.main).toEqual({ label: "PM10", value: "20.5", unit: "µg/m³" });
    expect(r.readings).toEqual([
      { label: "PM10", value: "20.5", unit: "µg/m³" },
      { label: "NO₂", value: "11", unit: "µg/m³", spread: "± 1.65" },
    ]);
    expect(r.observedAt).toBe("2026-11-14T05:00:00+00:00");
    expect(r.synthetic).toBe(false);
  });

  it("says when a sensor is simulated", () => {
    const data = normalizeLayer(loop);
    const r = describeResource(data.items[0]!, data, "traffic_flow");
    expect(r.synthetic).toBe(true);
    expect(r.title).toBe("Traffic sensor 009");
  });

  it("explains a count of antennas per cell", () => {
    const data = normalizeLayer({ type: "aggregate", cell_m: 500, total: 6, cells: [{ lon: 12.4, lat: 41.9, count: 5 }] });
    const r = describeResource(data.items[0]!, data, "antenna_register");
    expect(r.title).toBe("5 antenna sites");
    expect(r.category).toBe("Count in a 500 m square");
  });

  it("speaks Italian", () => {
    setLang("it");
    try {
      const data = normalizeLayer(hospital);
      const r = describeResource(data.items[0]!, data, "hospitals");
      expect(r.category).toBe("Ospedale");
      expect(r.facts).toContainEqual({ label: "Posti letto", value: "300" });
    } finally {
      setLang("en");
    }
  });
});
