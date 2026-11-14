import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Database, Home as HomeIcon, Megaphone, LogIn, Map as MapIcon, MessagesSquare, Trophy, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, WakingBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { VoiceButton } from "@/components/VoiceButton";
import { texts, tr } from "@/lib/i18n";
import { PUBLIC_SCREENS, STAFF_ACCESS_PATH, screenPath, screenText, type ScreenId } from "@/lib/tiers";
import CityView from "@/pages/CityView";
import Ask from "@/pages/Ask";
import DataHonesty from "@/pages/DataHonesty";
import Home from "@/pages/Home";
import Report from "@/pages/Report";
import Sport from "@/pages/Sport";
import StaffAccess from "@/pages/StaffAccess";
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
  city: { icon: MapIcon, el: <CityView audience="public" /> },
  sport: { icon: Trophy, el: <Sport /> },
  ask: { icon: MessagesSquare, el: <Ask audience="public" /> },
  report: { icon: Megaphone, el: <Report /> },
  honesty: { icon: Database, el: <DataHonesty /> },
};

/**
 * The public service for residents: PA-blue header, a few sections named in words across the top,
 * always light, no account. City personnel reach their workspace through "City staff sign-in".
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
          <div className="flex items-center gap-4 px-4 pt-2.5">
            <Brand tagline={t.tagline} />
            <div className="flex-1" />
            <VoiceButton />
            <LangSwitch />
            <Link
              to={STAFF_ACCESS_PATH}
              className="inline-flex min-h-9 items-center gap-1.5 rounded px-2.5 text-xs font-semibold text-chrome-muted underline-offset-2 transition-colors duration-150 hover:text-chrome-ink hover:underline"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              {t.staff}
            </Link>
          </div>
          <nav aria-label={t.nav} className="flex gap-1 overflow-x-auto px-3 pt-1.5">
            {PUBLIC_SCREENS.map((s) => {
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
      <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line bg-surface px-4 py-1.5 text-2xs text-muted">
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
