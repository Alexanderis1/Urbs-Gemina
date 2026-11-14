import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { needsCityView, onMapAction } from "@/lib/mapbus";
import { useSession } from "@/lib/runlog";
import { experienceOf, screenPath } from "@/lib/tiers";

/**
 * Handles open_screen, and switches to the map when a map action arrives while no map is showing.
 * Each experience has its own addresses; a screen the current one does not have is simply not opened.
 */
export function ScreenRouter() {
  const navigate = useNavigate();
  const experience = experienceOf(useSession().tier);
  useEffect(
    () =>
      onMapAction((a) => {
        const to = a.tool === "open_screen" ? screenPath(experience, a.args.screen) : needsCityView(a) ? screenPath(experience, "city") : null;
        if (to) navigate(to);
      }),
    [navigate, experience],
  );
  return null;
}
