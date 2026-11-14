import { describe, expect, it } from "vitest";
import { PUBLIC_SCREENS, STAFF_ACCESS_PATH, STAFF_SCREENS, canOpen, experienceOf, resolveTier, screenPath, screensFor } from "@/lib/tiers";

describe("role tiers (UI side; the server enforces the same rule)", () => {
  it("hides Admin and Permit check from citizens", () => {
    expect(canOpen("citizen", "admin")).toBe(false);
    expect(canOpen("citizen", "permit")).toBe(false);
    expect(canOpen("citizen", "city")).toBe(true);
  });
  it("lets the office tier open everything", () => {
    expect(canOpen("office", "admin")).toBe(true);
  });
});

describe("two experiences: a public service and a staff workspace", () => {
  it("anyone who is not city staff gets the public service", () => {
    expect(experienceOf("citizen")).toBe("public");
    expect(experienceOf("office")).toBe("staff");
  });

  it("the public service opens on the resident's own area and has no office tools", () => {
    expect(PUBLIC_SCREENS[0]).toMatchObject({ id: "home", path: "/" });
    const ids = PUBLIC_SCREENS.map((s) => s.id);
    expect(ids).toEqual(["home", "city", "sport", "ask", "honesty"]);
    expect(canOpen("citizen", "scenario")).toBe(false);
    expect(canOpen("citizen", "home")).toBe(true);
  });

  it("the staff workspace opens on the city and has every tool, but not the residents' home page", () => {
    expect(STAFF_SCREENS[0]).toMatchObject({ id: "city", path: "/" });
    expect(STAFF_SCREENS.map((s) => s.id)).toEqual(["city", "ask", "permit", "scenario", "sport", "honesty", "admin"]);
    expect(canOpen("office", "home")).toBe(false);
  });

  it("each experience has its own address for a screen", () => {
    expect(screenPath("staff", "city")).toBe("/");
    expect(screenPath("public", "city")).toBe("/map");
    expect(screenPath("public", "permit")).toBeNull();
    expect(screenPath("staff", "permit")).toBe("/permit");
  });

  it("no screen address is used twice inside one experience, and none hides the staff sign-in page", () => {
    for (const e of ["public", "staff"] as const) {
      const paths = screensFor(e).map((s) => s.path);
      expect(new Set(paths).size).toBe(paths.length);
      expect(paths).not.toContain(STAFF_ACCESS_PATH);
    }
  });

  it("the demo starts on the public service unless this browser chose the staff workspace", () => {
    expect(resolveTier(null)).toBe("citizen");
    expect(resolveTier("office")).toBe("office");
    expect(resolveTier("admin")).toBe("citizen");
  });
});
