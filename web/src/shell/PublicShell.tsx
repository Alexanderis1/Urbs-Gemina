import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Database, Home as HomeIcon, LogIn, Map as MapIcon, MessagesSquare, Trophy, type LucideIcon } from "lucide-react";
import { AiDisclosure, SampleModeBanner, WakingBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { VoiceButton } from "@/components/VoiceButton";
import { PUBLIC_SCREENS, STAFF_ACCESS_PATH, type ScreenId } from "@/lib/tiers";
import CityView from "@/pages/CityView";
import Ask from "@/pages/Ask";
import DataHonesty from "@/pages/DataHonesty";
import Home from "@/pages/Home";
import Sport from "@/pages/Sport";
import StaffAccess from "@/pages/StaffAccess";
import { Brand, SkipLink } from "./Brand";

const VIEW: Partial<Record<ScreenId, { icon: LucideIcon; el: JSX.Element }>> = {
  home: { icon: HomeIcon, el: <Home /> },
  city: { icon: MapIcon, el: <CityView audience="public" /> },
  sport: { icon: Trophy, el: <Sport /> },
  ask: { icon: MessagesSquare, el: <Ask audience="public" /> },
  honesty: { icon: Database, el: <DataHonesty /> },
};

/**
 * The public service for residents: PA-blue header, a few sections named in words across the top,
 * always light, no account. City personnel reach their workspace through "City staff sign-in".
 */
export function PublicShell() {
  return (
    <div className="flex h-full flex-col">
      <SkipLink />
      <ScreenRouter />
      <div className="chrome-public">
        <AiDisclosure audience="public" />
        <header className="bg-chrome text-chrome-ink">
          <div className="flex items-center gap-4 px-4 pt-2.5">
            <Brand tagline="Rome for residents" />
            <div className="flex-1" />
            <VoiceButton />
            <Link
              to={STAFF_ACCESS_PATH}
              className="inline-flex min-h-9 items-center gap-1.5 rounded px-2.5 text-xs font-semibold text-chrome-muted underline-offset-2 transition-colors duration-150 hover:text-chrome-ink hover:underline"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              City staff sign-in
            </Link>
          </div>
          <nav aria-label="Sections" className="flex gap-1 overflow-x-auto px-3 pt-1.5">
            {PUBLIC_SCREENS.map((s) => {
              const Icon = VIEW[s.id]!.icon;
              return (
                <NavLink
                  key={s.id}
                  to={s.path}
                  end
                  title={s.hint}
                  className={({ isActive }) =>
                    `inline-flex shrink-0 items-center gap-2 rounded-t border-b-[3px] px-3.5 py-2 text-sm font-semibold transition-colors duration-150 ${
                      isActive ? "border-white bg-white/10 text-white" : "border-transparent text-chrome-muted hover:bg-white/10 hover:text-white"
                    }`
                  }
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {s.label}
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
          Information only, not an alert service. <span className="font-semibold text-ink">In an emergency call 112.</span>
        </span>
        <span className="ml-auto">
          Every answer shows its sources.{" "}
          <Link to="/data" className="font-semibold text-link hover:underline">
            About the data
          </Link>
        </span>
      </footer>
    </div>
  );
}
