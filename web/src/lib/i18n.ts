// Italian first, English as a switch (Alessandro, 14 Nov 2026).
//
// How to write text:
//   const T = texts({
//     en: { title: "City view", cells: (n: number) => `${n} cells` },
//     it: { title: "Vista città", cells: (n: number) => `${n} celle` },
//   });
//   ... inside a component or a function:  const t = tr(T);  t.title, t.cells(3)
//
// `tr` reads the current language when it is called, so call it while rendering or inside a function,
// never at module load. Switching language remounts the app (App.tsx keys on it), so every text is read again.
// Text that comes from the service (warnings, refusal reasons, assistant answers) is shown as it arrives.
import { useSyncExternalStore } from "react";

export const LANGS = ["it", "en"] as const;
export type Lang = (typeof LANGS)[number];
export const LANG_LABEL: Record<Lang, string> = { it: "Italiano", en: "English" };
export const LANG_STORAGE_KEY = "urbs.lang";

export function resolveLang(stored: string | null): Lang {
  return stored === "en" ? "en" : "it";
}

function readStored(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(LANG_STORAGE_KEY);
  } catch {
    return null; // Storage can be blocked (private window): Italian.
  }
}

let current: Lang = resolveLang(readStored());
const listeners = new Set<() => void>();

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  if (lang === current) return;
  current = lang;
  if (typeof document !== "undefined") document.documentElement.lang = lang;
  try {
    if (typeof window !== "undefined") window.localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    // Not remembered; the choice still holds for this visit.
  }
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The current language, for components that must re-render when it changes (App, the language switch). */
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, getLang);
}

/** Declares one text in both languages. Both sides must have the same keys and shapes (checked by the compiler). */
export function texts<T>(both: Record<Lang, T>): Record<Lang, T> {
  return both;
}

/** The text for the current language. */
export function tr<T>(both: Record<Lang, T>): T {
  return both[current];
}

/** Locale for numbers and dates in the current language. */
export function locale(): string {
  return current === "it" ? "it-IT" : "en-GB";
}

if (typeof document !== "undefined") document.documentElement.lang = current;
