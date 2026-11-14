export type Tier = "citizen" | "office";
export type ScreenId = "city" | "ask" | "permit" | "scenario" | "honesty" | "sport" | "admin";

// UI convenience only. The tool API enforces the same rule server-side (citizens get aggregates only).
const OFFICE_ONLY: ReadonlySet<ScreenId> = new Set(["permit", "admin"]);

export function canOpen(tier: Tier, screen: ScreenId): boolean {
  return tier === "office" || !OFFICE_ONLY.has(screen);
}
