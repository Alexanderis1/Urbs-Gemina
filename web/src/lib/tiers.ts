// Who sees what. Two experiences share one twin:
//   public  the service for residents: no account, address first, plain words, a few public layers
//   staff   the operations workspace for city personnel: every tool, evidence and run ids, after sign-in
// UI convenience only. The tool API enforces what each tier may see (citizens get aggregates only).
// The reasoning is in web/docs/design-system.md, "Two experiences".
import { texts, tr } from "@/lib/i18n";

export type Tier = "citizen" | "office";
export type Experience = "public" | "staff";
export type ScreenId = "home" | "city" | "ask" | "permit" | "scenario" | "honesty" | "sport" | "admin" | "report" | "signals";

export function experienceOf(tier: Tier): Experience {
  return tier === "office" ? "staff" : "public";
}

export interface ScreenInfo {
  id: ScreenId;
  path: string;
}

export const PUBLIC_SCREENS: readonly ScreenInfo[] = [
  { id: "home", path: "/" },
  { id: "city", path: "/map" },
  { id: "sport", path: "/sport" },
  { id: "ask", path: "/ask" },
  { id: "report", path: "/segnala" },
  { id: "honesty", path: "/data" },
];

export const STAFF_SCREENS: readonly ScreenInfo[] = [
  { id: "city", path: "/" },
  { id: "ask", path: "/ask" },
  { id: "signals", path: "/segnalazioni" },
  { id: "permit", path: "/permit" },
  { id: "scenario", path: "/scenarios" },
  { id: "sport", path: "/sport" },
  { id: "honesty", path: "/data" },
  { id: "admin", path: "/admin" },
];

/** `label` is the name in the navigation; `hint` is one plain sentence on what the screen is for (tooltip). */
interface ScreenText {
  label: string;
  hint: string;
}

const SCREEN_TEXT = texts<Record<Experience, Partial<Record<ScreenId, ScreenText>>>>({
  en: {
    public: {
      home: { label: "My area", hint: "What is happening around your address" },
      city: { label: "City map", hint: "Air, rain, transport and services on the 3D map of Rome" },
      sport: { label: "Sport", hint: "Sports facilities near you and areas without them" },
      ask: { label: "Ask", hint: "Ask a question and get an answer with its sources" },
      report: { label: "Report", hint: "Tell the city about something happening near you, with a photo" },
      honesty: { label: "About the data", hint: "Where the information comes from and how far to trust it" },
    },
    staff: {
      city: { label: "City", hint: "Watch the city: 3D model and live layers" },
      signals: { label: "Reports", hint: "Citizen reports merged into live events, with how sure we are" },
      ask: { label: "Ask", hint: "Ask a question and get a cited answer" },
      permit: { label: "Permit", hint: "Check the context of a new antenna application" },
      scenario: { label: "Scenarios", hint: "Test a what-if: floods, heat, closures, antennas" },
      sport: { label: "Sport", hint: "Sports facilities and areas without them" },
      honesty: { label: "Data", hint: "Where every layer comes from and how far to trust it" },
      admin: { label: "Admin", hint: "Providers, legal thresholds and the audit log" },
    },
  },
  it: {
    public: {
      home: { label: "La mia zona", hint: "Che cosa succede intorno al tuo indirizzo" },
      city: { label: "Mappa della città", hint: "Aria, pioggia, trasporti e servizi sulla mappa 3D di Roma" },
      sport: { label: "Sport", hint: "Impianti sportivi vicino a te e zone che ne sono prive" },
      ask: { label: "Chiedi", hint: "Fai una domanda e ricevi una risposta con le sue fonti" },
      report: { label: "Segnala", hint: "Segnala alla città un evento vicino a te, con una foto" },
      honesty: { label: "I dati", hint: "Da dove vengono le informazioni e quanto fidarsi" },
    },
    staff: {
      city: { label: "Città", hint: "Osserva la città: modello 3D e livelli in tempo reale" },
      signals: { label: "Segnalazioni", hint: "Segnalazioni dei cittadini unite in eventi in corso, con il grado di fiducia" },
      ask: { label: "Chiedi", hint: "Fai una domanda e ricevi una risposta con le fonti" },
      permit: { label: "Istanze", hint: "Verifica il contesto di una nuova istanza per un'antenna" },
      scenario: { label: "Scenari", hint: "Prova un'ipotesi: alluvioni, caldo, chiusure, antenne" },
      sport: { label: "Sport", hint: "Impianti sportivi e zone che ne sono prive" },
      honesty: { label: "Dati", hint: "Da dove viene ogni livello e quanto fidarsi" },
      admin: { label: "Admin", hint: "Fornitori di dati, soglie di legge e registro delle esecuzioni" },
    },
  },
});

/** The name and tooltip of a screen in one experience, in the current language. */
export function screenText(experience: Experience, screen: ScreenId): ScreenText {
  return tr(SCREEN_TEXT)[experience][screen] ?? { label: screen, hint: "" };
}

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
