// ElevenLabs voice agents (WS9). The citizen agent is public, so the browser uses its id directly.
// The office agent is private: the "tools" edge function returns a signed URL, only for office sessions.
import { dispatchMapAction } from "./mapbus";

export const CITIZEN_AGENT_ID =
  (import.meta.env.VITE_ELEVENLABS_CITIZEN_AGENT_ID as string | undefined) || "agent_1501m7b8c0zpfxm9r3wq8cg1sz9b";

/** voice/client_tools.json: all fire-and-forget (expects_response false). */
export const VOICE_TOOL_NAMES = ["fly_to", "show_area", "show_layer", "show_radius", "open_screen"] as const;

type Handler = (parameters: Record<string, unknown>) => void;

export function buildClientTools(dispatch: (raw: unknown) => boolean = dispatchMapAction): Record<string, Handler> {
  return Object.fromEntries(
    VOICE_TOOL_NAMES.map((name) => [
      name,
      (parameters: Record<string, unknown>) => {
        // Validation (including "ignore points outside Rome") happens in parseMapAction.
        dispatch({ tool: name, args: parameters });
      },
    ]),
  );
}
