import { describe, expect, it } from "vitest";
import { setLang } from "@/lib/i18n";
import { macroAreas } from "@/lib/services";
import { PUBLIC_NAV, PUBLIC_SCREENS, screenPath } from "@/lib/tiers";

describe("the residents' services, grouped in macro-areas", () => {
  it("has the four macro-areas in the order of the navigation bar", () => {
    expect(macroAreas().map((a) => a.screen)).toEqual(["environment", "transport", "social", "report"]);
    expect(PUBLIC_NAV.slice(1).map((s) => s.id)).toEqual(macroAreas().map((a) => a.screen));
  });

  it("every service opens inside its own macro-area screen, or on another screen of the residents' service", () => {
    const screens = PUBLIC_SCREENS.map((s) => s.path);
    for (const area of macroAreas()) {
      const base = screenPath("public", area.screen)!;
      expect(area.services.length).toBeGreaterThan(0);
      for (const s of area.services) expect(s.to.startsWith(base) || screens.includes(s.to)).toBe(true);
    }
  });

  it("keeps the planning of a new sports facility within reach of residents, under Sociale", () => {
    const social = macroAreas().find((a) => a.screen === "social")!;
    expect(social.services.map((s) => s.id)).toEqual(["sport", "museums", "plan"]);
    expect(social.services[2]!.to).toBe(screenPath("public", "sport"));
  });

  it("offers the five kinds of report, each opening the report page on that kind", () => {
    const report = macroAreas().find((a) => a.screen === "report")!;
    expect(report.services.map((s) => s.to)).toEqual([
      "/segnala?tipo=flood",
      "/segnala?tipo=pothole",
      "/segnala?tipo=traffic",
      "/segnala?tipo=roadworks",
      "/segnala?tipo=public_event",
    ]);
  });

  it("is written in Italian and in English", () => {
    setLang("it");
    try {
      expect(macroAreas()[0]!.title).toBe("Ambiente");
      expect(macroAreas()[0]!.services[0]!.title).toBe("Com'è l'aria qui?");
    } finally {
      setLang("en");
    }
    expect(macroAreas()[0]!.title).toBe("Environment");
  });
});
