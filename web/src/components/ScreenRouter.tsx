import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { needsCityView, onMapAction } from "@/lib/mapbus";
import type { ActionScreen } from "@/lib/mapActions";

const PATHS: Record<ActionScreen, string> = { city: "/", ask: "/ask", permit: "/permit", scenario: "/scenarios", honesty: "/data" };

/** Handles open_screen, and switches to City view when a map action arrives while no map is showing. */
export function ScreenRouter() {
  const navigate = useNavigate();
  useEffect(
    () =>
      onMapAction((a) => {
        if (a.tool === "open_screen") navigate(PATHS[a.args.screen]);
        else if (needsCityView(a)) navigate("/");
      }),
    [navigate],
  );
  return null;
}
