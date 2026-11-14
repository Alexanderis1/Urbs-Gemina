import { describe, expect, it } from "vitest";
import { ALPHA_FLOOR, RAMP, confidenceAlpha, rampColor, rampGradient } from "@/lib/colors";

describe("value ramp", () => {
  it("builds the legend gradient from the same stops the map uses", () => {
    const g = rampGradient();
    expect(g.startsWith("linear-gradient(90deg,")).toBe(true);
    for (const [r, gr, b] of RAMP) expect(g).toContain(`rgb(${r} ${gr} ${b})`);
    // First and last stops sit at the ends, matching rampColor(0) and rampColor(1).
    expect(g).toContain(`rgb(${rampColor(0).join(" ")}) 0%`);
    expect(g).toContain(`rgb(${RAMP[RAMP.length - 1]!.join(" ")}) 100%`);
  });
});

describe("confidence alpha", () => {
  it("keeps the old behaviour by default", () => {
    expect(confidenceAlpha(0, 0)).toBe(200);
    expect(confidenceAlpha(0, 10)).toBe(220);
    expect(confidenceAlpha(10, 10)).toBe(40);
  });
  it("never drops below the floor, so faint cells stay visible on a dark map", () => {
    expect(confidenceAlpha(10, 10, ALPHA_FLOOR.dark)).toBe(ALPHA_FLOOR.dark);
    expect(confidenceAlpha(0, 10, ALPHA_FLOOR.dark)).toBe(220);
    expect(ALPHA_FLOOR.dark).toBeGreaterThan(ALPHA_FLOOR.light);
  });
});
