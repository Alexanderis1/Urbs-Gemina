import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Database, FlaskConical, Map as MapIcon, MessagesSquare, Moon, RadioTower, Settings2, Sun, Trophy, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, StatusBar } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { Account } from "@/components/Account";
import { VoiceButton } from "@/components/VoiceButton";
import { canOpen, type ScreenId } from "@/lib/tiers";
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

// `hint` is the tooltip: one plain sentence on what the screen is for.
const SCREENS: { id: ScreenId; path: string; label: string; hint: string; icon: LucideIcon; el: JSX.Element }[] = [
  { id: "city", path: "/", label: "City", hint: "Watch the city: 3D model and live layers", icon: MapIcon, el: <CityView /> },
  { id: "ask", path: "/ask", label: "Ask", hint: "Ask a question and get a cited answer", icon: MessagesSquare, el: <Ask /> },
  { id: "permit", path: "/permit", label: "Permit", hint: "Check the context of a new antenna application", icon: RadioTower, el: <PermitCheck /> },
  { id: "scenario", path: "/scenarios", label: "Scenarios", hint: "Test a what-if: floods, heat, closures, antennas", icon: FlaskConical, el: <ScenarioLab /> },
  { id: "sport", path: "/sport", label: "Sport", hint: "Sports facilities and areas without them", icon: Trophy, el: <Sport /> },
  { id: "honesty", path: "/data", label: "Data", hint: "Where every layer comes from and how far to trust it", icon: Database, el: <DataHonesty /> },
  { id: "admin", path: "/admin", label: "Admin", hint: "Providers, legal thresholds and the audit log", icon: Settings2, el: <Admin /> },
];

/** Two overlapping squares: the city and its twin. */
function Logo() {
  return (
    <svg viewBox="0 0 28 28" className="h-7 w-7" aria-hidden="true">
      <rect x="2" y="2" width="16" height="16" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect x="10" y="10" width="16" height="16" rx="1.5" fill="rgb(var(--c-primary))" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export default function App() {
  const { tier } = useSession();
  const { theme, toggle } = useTheme();
  const visible = SCREENS.filter((s) => canOpen(tier, s.id));
  return (
    <div className="flex h-full flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <ScreenRouter />
      <AiDisclosure />
      <header className="flex items-center gap-4 bg-chrome px-4 py-2 text-chrome-ink">
        <div className="flex items-center gap-2.5">
          <Logo />
          <div className="leading-tight">
            <div className="text-lg font-bold tracking-tight">Urbs Gemina</div>
            <div className="text-2xs uppercase tracking-[0.1em] text-chrome-muted">Digital twin of Rome</div>
          </div>
        </div>
        <div className="flex-1" />
        <VoiceButton />
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded border border-chrome-line text-chrome-muted transition-colors duration-150 hover:border-white hover:text-chrome-ink"
          onClick={toggle}
          title={`Theme: ${THEME_LABEL[theme]}. Click to switch.`}
          aria-label={`Switch to the ${theme === "light" ? "dark operations-room" : "light institutional"} theme`}
        >
          {theme === "light" ? <Moon className="h-4 w-4" aria-hidden="true" /> : <Sun className="h-4 w-4" aria-hidden="true" />}
        </button>
        <Account />
      </header>
      <SampleModeBanner />
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Screens" className="flex w-[4.5rem] shrink-0 flex-col gap-0.5 border-r border-line bg-surface py-2">
          {visible.map((s) => (
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
                  <s.icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.8} aria-hidden="true" />
                  {s.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <main id="main" className="min-h-0 min-w-0 flex-1">
          <Routes>
            {visible.map((s) => (
              <Route key={s.id} path={s.path} element={s.el} />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <StatusBar />
    </div>
  );
}
