import { describe, expect, it } from "vitest";
import { canOpen } from "@/lib/tiers";

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
