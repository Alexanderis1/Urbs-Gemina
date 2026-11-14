import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Database, FlaskConical, LogOut, Map as MapIcon, MessagesSquare, Moon, RadioTower, Settings2, ShieldCheck, Sun, Trophy, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, StatusBar, WakingBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { VoiceButton } from "@/components/VoiceButton";
import { supabase } from "@/integrations/supabase/client";
import { texts, tr } from "@/lib/i18n";
import { STAFF_SCREENS, screenText, type ScreenId } from "@/lib/tiers";
import { useSession } from "@/lib/runlog";
import { THEME_LABEL } from "@/lib/theme";
import { useTheme } from "@/lib/useTheme";
import CityView from "@/pages/CityView";
import Ask from "@/pages/Ask";
import PermitCheck from "@/pages/PermitCheck";
import ScenarioLab from "@/pages/ScenarioLab";
import DataHonesty from "@/pages/DataHonesty";
import Admin from "@/pages/Admin";
import Sport from "@/pages/Sport";
import { Brand, LangSwitch, SkipLink } from "./Brand";

const T = texts({
  en: {
    tagline: "Operations workspace",
    badge: "City staff",
    demo: "demo",
    badgeHint: "You are signed in as city staff. Residents see a simpler public service.",
    theme: (label: string) => `Theme: ${label}. Click to switch.`,
    toDark: "Switch to the dark operations-room theme",
    toLight: "Switch to the light institutional theme",
    signOut: "Sign out",
    signOutHint: "Leave the workspace and go back to the public service",
    nav: "Workspace tools",
  },
  it: {
    tagline: "Sala operativa",
    badge: "Personale del Comune",
    demo: "demo",
    badgeHint: "Hai effettuato l'accesso come personale del Comune. I cittadini vedono un servizio pubblico più semplice.",
    theme: (label: string) => `Tema: ${label}. Clicca per cambiare.`,
    toDark: "Passa al tema scuro da sala operativa",
    toLight: "Passa al tema chiaro istituzionale",
    signOut: "Esci",
    signOutHint: "Lascia la sala operativa e torna al servizio pubblico",
    nav: "Strumenti della sala operativa",
  },
});

const VIEW: Partial<Record<ScreenId, { icon: LucideIcon; el: JSX.Element }>> = {
  city: { icon: MapIcon, el: <CityView audience="staff" /> },
  ask: { icon: MessagesSquare, el: <Ask audience="staff" /> },
  permit: { icon: RadioTower, el: <PermitCheck /> },
  scenario: { icon: FlaskConical, el: <ScenarioLab /> },
  sport: { icon: Trophy, el: <Sport /> },
  honesty: { icon: Database, el: <DataHonesty /> },
  admin: { icon: Settings2, el: <Admin /> },
};

const HEADER_BUTTON =
  "inline-flex min-h-9 items-center gap-1.5 rounded border border-chrome-line px-2.5 text-xs font-semibold text-chrome-muted transition-colors duration-150 hover:border-white hover:text-chrome-ink";

/**
 * The operations workspace for city personnel: navy header, icon rail with every tool, dense panels,
 * the run log in the status bar, light or dark theme. Reached only after staff sign-in.
 */
export function StaffShell() {
  const { setTier } = useSession();
  const { theme, toggle } = useTheme();
  const t = tr(T);
  // Demo (no Lovable Cloud): leaving just returns to the public service. With Cloud it signs the officer out.
  const leave = () => (supabase ? void supabase.auth.signOut() : setTier?.("citizen"));
  return (
    <div className="flex h-full flex-col">
      <SkipLink />
      <ScreenRouter />
      <AiDisclosure audience="staff" />
      <header className="flex items-center gap-4 bg-chrome px-4 py-2 text-chrome-ink">
        <Brand tagline={t.tagline} />
        <span
          className="inline-flex items-center gap-1 rounded-sm border border-chrome-line px-1.5 py-0.5 text-2xs font-bold uppercase tracking-[0.08em] text-chrome-ink"
          title={t.badgeHint}
        >
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          {t.badge}
          {supabase ? "" : ` · ${t.demo}`}
        </span>
        <div className="flex-1" />
        <VoiceButton />
        <LangSwitch />
        <button
          className={`${HEADER_BUTTON} w-9 justify-center px-0`}
          onClick={toggle}
          title={t.theme(THEME_LABEL[theme])}
          aria-label={theme === "light" ? t.toDark : t.toLight}
        >
          {theme === "light" ? <Moon className="h-4 w-4" aria-hidden="true" /> : <Sun className="h-4 w-4" aria-hidden="true" />}
        </button>
        <button className={HEADER_BUTTON} onClick={leave} title={t.signOutHint}>
          <LogOut className="h-4 w-4" aria-hidden="true" />
          {t.signOut}
        </button>
      </header>
      <SampleModeBanner />
      <WakingBanner />
      <div className="flex min-h-0 flex-1">
        <nav aria-label={t.nav} className="flex w-[4.5rem] shrink-0 flex-col gap-0.5 border-r border-line bg-surface py-2">
          {STAFF_SCREENS.map((s) => {
            const Icon = VIEW[s.id]!.icon;
            const text = screenText("staff", s.id);
            return (
              <NavLink
                key={s.id}
                to={s.path}
                end
                title={text.hint}
                className={({ isActive }) =>
                  `group relative mx-1 flex flex-col items-center gap-0.5 rounded px-1 py-2 text-2xs font-semibold transition-colors duration-150 ${
                    isActive ? "bg-primary-soft text-link" : "text-muted hover:bg-sunken hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className={`absolute -left-1 top-2 h-8 w-0.5 rounded-r bg-link transition-opacity duration-150 ${isActive ? "opacity-100" : "opacity-0"}`} />
                    <Icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.8} aria-hidden="true" />
                    {text.label}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
        <main id="main" className="min-h-0 min-w-0 flex-1">
          <Routes>
            {STAFF_SCREENS.map((s) => (
              <Route key={s.id} path={s.path} element={VIEW[s.id]!.el} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <StatusBar />
    </div>
  );
}
