import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AiDisclosure, SampleModeBanner } from "@/components/Banners";
import { ScreenRouter } from "@/components/ScreenRouter";
import { canOpen, type ScreenId } from "@/lib/tiers";
import { useSession } from "@/lib/runlog";
import CityView from "@/pages/CityView";
import Ask from "@/pages/Ask";
import PermitCheck from "@/pages/PermitCheck";
import ScenarioLab from "@/pages/ScenarioLab";
import DataHonesty from "@/pages/DataHonesty";
import Admin from "@/pages/Admin";
import Sport from "@/pages/Sport";

const SCREENS: { id: ScreenId; path: string; label: string; el: JSX.Element }[] = [
  { id: "city", path: "/", label: "City view", el: <CityView /> },
  { id: "ask", path: "/ask", label: "Ask", el: <Ask /> },
  { id: "permit", path: "/permit", label: "Permit check", el: <PermitCheck /> },
  { id: "scenario", path: "/scenarios", label: "Scenario lab", el: <ScenarioLab /> },
  { id: "honesty", path: "/data", label: "Data honesty", el: <DataHonesty /> },
  { id: "sport", path: "/sport", label: "Sport", el: <Sport /> },
  { id: "admin", path: "/admin", label: "Admin", el: <Admin /> },
];

export default function App() {
  const { tier, setTier } = useSession();
  const visible = SCREENS.filter((s) => canOpen(tier, s.id));
  return (
    <div className="flex h-full flex-col">
      <ScreenRouter />
      <AiDisclosure />
      <SampleModeBanner />
      <header className="flex items-center gap-4 border-b border-stone-200 bg-white px-4 py-2">
        <div className="font-serif text-lg font-bold text-roma">Urbs Gemina</div>
        <nav className="flex flex-1 flex-wrap gap-1">
          {visible.map((s) => (
            <NavLink
              key={s.id}
              to={s.path}
              end
              className={({ isActive }) =>
                `rounded px-2 py-1 text-sm ${isActive ? "bg-roma text-white" : "text-stone-700 hover:bg-stone-100"}`
              }
            >
              {s.label}
            </NavLink>
          ))}
        </nav>
        {/* Demo switch. With Supabase auth the tier comes from the user's role and is enforced server-side. */}
        <select className="rounded border border-stone-300 px-2 py-1 text-sm" value={tier} onChange={(e) => setTier(e.target.value as typeof tier)}>
          <option value="office">Office</option>
          <option value="citizen">Citizen</option>
        </select>
      </header>
      <main className="min-h-0 flex-1">
        <Routes>
          {visible.map((s) => (
            <Route key={s.id} path={s.path} element={s.el} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
