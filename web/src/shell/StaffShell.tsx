import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Database, FlaskConical, LogOut, Map as MapIcon, MessagesSquare, Moon, RadioTower, Settings2, ShieldCheck, Sun, Trophy, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, StatusBar, WakingBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { VoiceButton } from "@/components/VoiceButton";
import { supabase } from "@/integrations/supabase/client";
import { STAFF_SCREENS, type ScreenId } from "@/lib/tiers";
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
import { Brand, SkipLink } from "./Brand";

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
  // Demo (no Lovable Cloud): leaving just returns to the public service. With Cloud it signs the officer out.
  const leave = () => (supabase ? void supabase.auth.signOut() : setTier?.("citizen"));
  return (
    <div className="flex h-full flex-col">
      <SkipLink />
      <ScreenRouter />
      <AiDisclosure audience="staff" />
      <header className="flex items-center gap-4 bg-chrome px-4 py-2 text-chrome-ink">
        <Brand tagline="Operations workspace" />
        <span
          className="inline-flex items-center gap-1 rounded-sm border border-chrome-line px-1.5 py-0.5 text-2xs font-bold uppercase tracking-[0.08em] text-chrome-ink"
          title="You are signed in as city staff. Residents see a simpler public service."
        >
          <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
          City staff{supabase ? "" : " · demo"}
        </span>
        <div className="flex-1" />
        <VoiceButton />
        <button
          className={`${HEADER_BUTTON} w-9 justify-center px-0`}
          onClick={toggle}
          title={`Theme: ${THEME_LABEL[theme]}. Click to switch.`}
          aria-label={`Switch to the ${theme === "light" ? "dark operations-room" : "light institutional"} theme`}
        >
          {theme === "light" ? <Moon className="h-4 w-4" aria-hidden="true" /> : <Sun className="h-4 w-4" aria-hidden="true" />}
        </button>
        <button className={HEADER_BUTTON} onClick={leave} title="Leave the workspace and go back to the public service">
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign out
        </button>
      </header>
      <SampleModeBanner />
      <WakingBanner />
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Workspace tools" className="flex w-[4.5rem] shrink-0 flex-col gap-0.5 border-r border-line bg-surface py-2">
          {STAFF_SCREENS.map((s) => {
            const Icon = VIEW[s.id]!.icon;
            return (
              <NavLink
                key={s.id}
                to={s.path}
                end
                title={s.hint}
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
                    {s.label}
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
