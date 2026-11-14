// Who sees what. Two experiences share one twin:
//   public  the service for residents: no account, address first, plain words, a few public layers
//   staff   the operations workspace for city personnel: every tool, evidence and run ids, after sign-in
// UI convenience only. The tool API enforces what each tier may see (citizens get aggregates only).
// The reasoning is in web/docs/design-system.md, "Two experiences".

export type Tier = "citizen" | "office";
export type Experience = "public" | "staff";
export type ScreenId = "home" | "city" | "ask" | "permit" | "scenario" | "honesty" | "sport" | "admin";

export function experienceOf(tier: Tier): Experience {
  return tier === "office" ? "staff" : "public";
}

export interface ScreenInfo {
  id: ScreenId;
  path: string;
  label: string;
  /** One plain sentence on what the screen is for (tooltip). */
  hint: string;
}

export const PUBLIC_SCREENS: readonly ScreenInfo[] = [
  { id: "home", path: "/", label: "My area", hint: "What is happening around your address" },
  { id: "city", path: "/map", label: "City map", hint: "Air, rain, transport and services on the 3D map of Rome" },
  { id: "sport", path: "/sport", label: "Sport", hint: "Sports facilities near you and areas without them" },
  { id: "ask", path: "/ask", label: "Ask", hint: "Ask a question and get an answer with its sources" },
  { id: "honesty", path: "/data", label: "About the data", hint: "Where the information comes from and how far to trust it" },
];

export const STAFF_SCREENS: readonly ScreenInfo[] = [
  { id: "city", path: "/", label: "City", hint: "Watch the city: 3D model and live layers" },
  { id: "ask", path: "/ask", label: "Ask", hint: "Ask a question and get a cited answer" },
  { id: "permit", path: "/permit", label: "Permit", hint: "Check the context of a new antenna application" },
  { id: "scenario", path: "/scenarios", label: "Scenarios", hint: "Test a what-if: floods, heat, closures, antennas" },
  { id: "sport", path: "/sport", label: "Sport", hint: "Sports facilities and areas without them" },
  { id: "honesty", path: "/data", label: "Data", hint: "Where every layer comes from and how far to trust it" },
  { id: "admin", path: "/admin", label: "Admin", hint: "Providers, legal thresholds and the audit log" },
];

/** Where city personnel sign in. Reachable from the public service only. */
export const STAFF_ACCESS_PATH = "/staff";

export function screensFor(experience: Experience): readonly ScreenInfo[] {
  return experience === "staff" ? STAFF_SCREENS : PUBLIC_SCREENS;
}

/** The address of a screen in one experience, or null when that experience does not have it. */
export function screenPath(experience: Experience, screen: ScreenId): string | null {
  return screensFor(experience).find((s) => s.id === screen)?.path ?? null;
}

export function canOpen(tier: Tier, screen: ScreenId): boolean {
  return screenPath(experienceOf(tier), screen) !== null;
}

/** Demo only (no Lovable Cloud): the experience chosen in this browser. With Cloud the tier comes from the user's role. */
export const TIER_STORAGE_KEY = "urbs.tier";

export function resolveTier(stored: string | null): Tier {
  return stored === "office" ? "office" : "citizen";
}
