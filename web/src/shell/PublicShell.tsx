import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Bus, Database, Home as HomeIcon, Megaphone, LogIn, Map as MapIcon, MessagesSquare, Trophy, Users, Wind, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, WakingBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { VoiceButton } from "@/components/VoiceButton";
import { texts, tr } from "@/lib/i18n";
import { PUBLIC_NAV, PUBLIC_SCREENS, STAFF_ACCESS_PATH, screenPath, screenText, type ScreenId } from "@/lib/tiers";
import CityView from "@/pages/CityView";
import Ask from "@/pages/Ask";
import DataHonesty from "@/pages/DataHonesty";
import Environment from "@/pages/Environment";
import Home from "@/pages/Home";
import Report from "@/pages/Report";
import Social from "@/pages/Social";
import Sport from "@/pages/Sport";
import StaffAccess from "@/pages/StaffAccess";
import Transport from "@/pages/Transport";
import { Brand, LangSwitch, SkipLink } from "./Brand";

const T = texts({
  en: {
    tagline: "Rome for residents",
    staff: "City staff sign-in",
    nav: "Sections",
    infoOnly: "Information only, not an alert service.",
    call112: "In an emergency call 112.",
    sources: "Every answer shows its sources.",
  },
  it: {
    tagline: "Roma per i cittadini",
    staff: "Accesso personale del Comune",
    nav: "Sezioni",
    infoOnly: "Solo informazioni, non un servizio di allerta.",
    call112: "In caso di emergenza chiama il 112.",
    sources: "Ogni risposta mostra le sue fonti.",
  },
});

const VIEW: Partial<Record<ScreenId, { icon: LucideIcon; el: JSX.Element }>> = {
  home: { icon: HomeIcon, el: <Home /> },
  environment: { icon: Wind, el: <Environment /> },
  transport: { icon: Bus, el: <Transport /> },
  social: { icon: Users, el: <Social /> },
  city: { icon: MapIcon, el: <CityView audience="public" /> },
  sport: { icon: Trophy, el: <Sport /> },
  ask: { icon: MessagesSquare, el: <Ask audience="public" /> },
  report: { icon: Megaphone, el: <Report /> },
  honesty: { icon: Database, el: <DataHonesty /> },
};

/**
 * The public service for residents, mobile first: PA-blue header, always light, no account. The home page and
 * the four macro-areas are a bar at the bottom of a phone and tabs across the top of a desk screen.
 * City personnel reach their workspace through "City staff sign-in".
 */
export function PublicShell() {
  const t = tr(T);
  return (
    <div className="flex h-full flex-col">
      <SkipLink />
      <ScreenRouter />
      <div className="chrome-public">
        <AiDisclosure audience="public" />
        <header className="bg-chrome text-chrome-ink">
          <div className="flex items-center gap-2 px-3 py-2 md:gap-4 md:px-4 md:pb-0 md:pt-2.5">
            <Link to="/" className="rounded text-chrome-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">
              <Brand tagline={t.tagline} />
            </Link>
            <div className="flex-1" />
            <div className="hidden sm:block">
              <VoiceButton />
            </div>
            <LangSwitch />
            <Link
              to={STAFF_ACCESS_PATH}
              title={t.staff}
              aria-label={t.staff}
              className="inline-flex min-h-9 items-center gap-1.5 rounded px-2 text-xs font-semibold text-chrome-muted underline-offset-2 transition-colors duration-150 hover:text-chrome-ink hover:underline md:px-2.5"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              <span className="hidden md:inline">{t.staff}</span>
            </Link>
          </div>
          <nav aria-label={t.nav} className="hidden gap-1 overflow-x-auto px-3 pt-1.5 md:flex">
            {PUBLIC_NAV.map((s) => {
              const Icon = VIEW[s.id]!.icon;
              const text = screenText("public", s.id);
              return (
                <NavLink
                  key={s.id}
                  to={s.path}
                  end
                  title={text.hint}
                  className={({ isActive }) =>
                    `inline-flex shrink-0 items-center gap-2 rounded-t border-b-[3px] px-3.5 py-2 text-sm font-semibold transition-colors duration-150 ${
                      isActive ? "border-white bg-white/10 text-white" : "border-transparent text-chrome-muted hover:bg-white/10 hover:text-white"
                    }`
                  }
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {text.label}
                </NavLink>
              );
            })}
          </nav>
        </header>
      </div>
      <SampleModeBanner />
      <WakingBanner />
      <main id="main" className="min-h-0 min-w-0 flex-1">
        <Routes>
          {PUBLIC_SCREENS.map((s) => (
            <Route key={s.id} path={s.path} element={VIEW[s.id]!.el} />
          ))}
          <Route path={STAFF_ACCESS_PATH} element={<StaffAccess />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {/* Phone: the home page and the four macro-areas, always under the thumb. */}
      <nav aria-label={t.nav} className="grid shrink-0 grid-cols-5 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden">
        {PUBLIC_NAV.map((s) => {
          const Icon = VIEW[s.id]!.icon;
          const text = screenText("public", s.id);
          return (
            <NavLink
              key={s.id}
              to={s.path}
              end
              className={({ isActive }) =>
                `flex min-h-14 flex-col items-center justify-center gap-0.5 border-t-[3px] px-1 text-[0.6875rem] font-semibold leading-tight transition-colors duration-150 ${
                  isActive ? "border-primary bg-primary-soft text-link" : "border-transparent text-muted hover:text-ink"
                }`
              }
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              {text.label}
            </NavLink>
          );
        })}
      </nav>
      <footer className="hidden flex-wrap items-center gap-x-4 gap-y-1 border-t border-line bg-surface px-4 py-1.5 text-2xs text-muted md:flex">
        <span>
          {t.infoOnly} <span className="font-semibold text-ink">{t.call112}</span>
        </span>
        <span className="ml-auto">
          {t.sources}{" "}
          <Link to={screenPath("public", "honesty") ?? "/"} className="font-semibold text-link hover:underline">
            {screenText("public", "honesty").label}
          </Link>
        </span>
      </footer>
    </div>
  );
}
