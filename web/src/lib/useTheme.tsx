import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { MAP_PALETTE, resolveTheme, THEME_STORAGE_KEY, type MapPalette, type Theme } from "./theme";

interface ThemeState {
  theme: Theme;
  palette: MapPalette;
  toggle: () => void;
}

const Ctx = createContext<ThemeState | null>(null);

function initial(): Theme {
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    // Storage can be blocked (private window): fall back to the system preference.
  }
  return resolveTheme(stored, window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
}

/** Holds the light / dark choice, writes it on <html data-theme> and remembers it in this browser. */
export function ThemeProvider({ force, children }: { force?: Theme; children: ReactNode }) {
  const [chosen, setChosen] = useState<Theme>(initial);
  // `force` wins while it is set (the public service is always light) but does not overwrite the remembered choice.
  const theme = force ?? chosen;
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, chosen);
    } catch {
      // Not remembered; the choice still holds for this visit.
    }
  }, [chosen]);
  const toggle = useCallback(() => setChosen((t) => (t === "light" ? "dark" : "light")), []);
  const value = useMemo(() => ({ theme, palette: MAP_PALETTE[theme], toggle }), [theme, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeState {
  const t = useContext(Ctx);
  if (!t) throw new Error("useTheme outside ThemeProvider");
  return t;
}
