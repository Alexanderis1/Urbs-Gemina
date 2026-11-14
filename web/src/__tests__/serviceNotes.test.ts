import { afterEach, describe, expect, it } from "vitest";
import { setLang } from "@/lib/i18n";
import { serviceNote } from "@/lib/serviceNotes";

describe("notes from the service in the reader's language", () => {
  afterEach(() => setLang("en"));

  it("leaves English notes as they are in English", () => {
    expect(serviceNote("Place not found in Rome.")).toEqual({ text: "Place not found in Rome.", translated: true });
  });

  it("says the usual notes in Italian, keeping the numbers and names", () => {
    setLang("it");
    expect(serviceNote("Place not found in Rome.").text).toBe("Luogo non trovato a Roma.");
    expect(serviceNote("10 readings older than the layer time were skipped").text).toBe("10 rilevazioni più vecchie dell'ora del livello non sono state usate.");
    expect(serviceNote("Large area: 144 records, 50 returned, picked evenly across the area. Ask for a smaller area (a municipio or a zone) to see every record.").text).toBe(
      "Area grande: 144 elementi, ne sono mostrati 50 scelti in modo uniforme. Scegli un'area più piccola (un municipio o una zona) per vederli tutti.",
    );
    expect(serviceNote("Only 70 of 219 places have readable opening hours; the others are listed as unknown.").text).toBe(
      "Solo 70 luoghi su 219 hanno orari leggibili; per gli altri gli orari non sono noti.",
    );
    expect(serviceNote("uncertainty is uncalibrated: not checked yet (no leave-one-station-out run on this layer)").text).toBe(
      "Incertezza non ancora calibrata: l'intervallo è indicativo.",
    );
    expect(serviceNote("Instantaneous worst-case estimate; the attention value is a 24-hour average.").translated).toBe(true);
  });

  it("marks a note it cannot translate, so the screen can fold it away", () => {
    setLang("it");
    const n = serviceNote("Something new the service says.");
    expect(n).toEqual({ text: "Something new the service says.", translated: false });
  });
});
