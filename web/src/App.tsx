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
  const staff = experienceOf(tier) === "staff";
  // The public service is always light; the dark "operations room" theme belongs to the workspace.
  return <ThemeProvider force={staff ? undefined : "light"}>{staff ? <StaffShell /> : <PublicShell />}</ThemeProvider>;
}
