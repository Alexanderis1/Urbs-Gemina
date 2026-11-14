import { describe, expect, it } from "vitest";
import { KIND_META, MAP_PALETTE, contrastRatio, resolveTheme, THEMES } from "@/lib/theme";
import { buildingColor } from "@/lib/buildingStyles";

describe("theme", () => {
  it("uses the stored theme when it is valid, else the system preference", () => {
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme("purple", false)).toBe("light");
  });

  it("has a map palette for every theme", () => {
    for (const t of THEMES) {
      expect(MAP_PALETTE[t].accent).toHaveLength(3);
      expect(MAP_PALETTE[t].background).toMatch(/^#/);
    }
  });

  it("gives every data kind a label, a hint and its own glyph", () => {
    const glyphs = new Set(Object.values(KIND_META).map((m) => m.glyph));
    expect(glyphs.size).toBe(Object.keys(KIND_META).length);
    for (const m of Object.values(KIND_META)) {
      expect(m.label.length).toBeGreaterThan(0);
      expect(m.hint.length).toBeGreaterThan(0);
    }
  });

  it("keeps label colours at AA contrast (4.5:1) on their surface in both themes", () => {
    for (const t of THEMES) {
      const p = MAP_PALETTE[t];
      for (const hex of Object.values(p.text)) {
        expect(contrastRatio(hex, p.surface)).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("draws plain buildings in the theme's colours", () => {
    expect(JSON.stringify(buildingColor("plain", "light"))).toContain(MAP_PALETTE.light.building);
    expect(JSON.stringify(buildingColor("plain", "dark"))).toContain(MAP_PALETTE.dark.building);
  });
});
