import { useLang } from "@/lib/i18n";
import { experienceOf } from "@/lib/tiers";
import { useSession } from "@/lib/runlog";
import { ThemeProvider } from "@/lib/useTheme";
import { PublicShell } from "@/shell/PublicShell";
import { StaffShell } from "@/shell/StaffShell";

/**
 * One twin, two experiences (web/docs/design-system.md, "Two experiences"):
 * residents get the public service, signed-in city personnel get the operations workspace.
 */
export default function App() {
  const { tier } = useSession();
  const lang = useLang();
  const staff = experienceOf(tier) === "staff";
  // The public service is always light; the dark "operations room" theme belongs to the workspace.
  // Keyed on the language: switching it remounts the screens, so every text is read again (lib/i18n.ts).
  return (
    <ThemeProvider key={lang} force={staff ? undefined : "light"}>
      {staff ? <StaffShell /> : <PublicShell />}
    </ThemeProvider>
  );
}
