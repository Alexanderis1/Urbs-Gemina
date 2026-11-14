import { describe, expect, it } from "vitest";
import { BUILDING_VIEWS, LEGENDS, roofLabel } from "@/lib/buildingStyles";
import { setLang } from "@/lib/i18n";

describe("building view wording", () => {
  it("speaks English by default", () => {
    expect(BUILDING_VIEWS.map((v) => v.label)).toEqual(["Plain", "Height uncertainty", "Ground motion (InSAR)", "Roof material"]);
    expect(LEGENDS.height_sd.low).toBe("0 m (sure)");
    expect(roofLabel("clay_tiles")).toBe("clay tiles");
  });
  it("speaks Italian", () => {
    setLang("it");
    try {
      expect(BUILDING_VIEWS[1]!.label).toBe("Incertezza sull'altezza");
      expect(LEGENDS.height_sd.high).toBe("6 m+ (incerto)");
      expect(roofLabel("green_roof")).toBe("tetto verde");
    } finally {
      setLang("en");
    }
  });
});
