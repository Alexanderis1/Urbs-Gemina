import { describe, expect, it } from "vitest";
import { contextMeaning, contextRows, contextSummary } from "@/lib/context";
import { setLang } from "@/lib/i18n";

const result = {
  groups: { sensitive_site: { label: "Sites", layers: [{ layer: "schools", label: "Schools", status: "ok", hits: [{ distance_m: 10, name: null }] }] } },
};

describe("context rows", () => {
  it("names an unnamed hit in English", () => {
    expect(contextRows(result)[0]!.name).toBe("(unnamed)");
  });

  it("speaks Italian", () => {
    setLang("it");
    try {
      expect(contextRows(result)[0]!.name).toBe("(senza nome)");
    } finally {
      setLang("en");
    }
  });

  it("names the layers and the 'not a prohibition' line in Italian, keeping unknown ones as they are", () => {
    const live = {
      meaning: "Context information only. Not a prohibition (Consiglio di Stato, Sez. IV, 2021).",
      groups: {
        constraint: {
          label: "Constraints",
          layers: [
            { layer: "unesco", label: "UNESCO World Heritage site", status: "ok", hits: [{ distance_m: 0, name: "Centro storico di Roma" }] },
            { layer: "cpq_edilizia_speciale", label: "Carta per la Qualita: special buildings", status: "ok", hits: [{ distance_m: 5, name: "x" }] },
            { layer: "something_new", label: "Something new", status: "ok", hits: [{ distance_m: 9, name: "y" }] },
            { layer: "ptpr_paesaggi_roma", label: "PTPR Tavola A (landscape systems)", status: "not_available" },
          ],
        },
      },
    };
    setLang("it");
    try {
      expect(contextRows(live).map((r) => r.layerLabel)).toEqual(["Sito UNESCO Patrimonio dell'Umanità", "Carta per la Qualità: edifici speciali", "Something new"]);
      expect(contextSummary(live).unavailable).toEqual(["PTPR Tavola A: sistemi di paesaggio"]);
      expect(contextMeaning(live.meaning)).toBe("Solo informazioni di contesto, non un divieto (Consiglio di Stato, Sez. IV, 2021).");
    } finally {
      setLang("en");
    }
    expect(contextRows(live)[0]!.layerLabel).toBe("UNESCO World Heritage site");
    expect(contextMeaning(live.meaning)).toBe(live.meaning);
  });
});
