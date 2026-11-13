import { useMemo, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import { isSampleMode, proxyFetch } from "@/api/client";
import { buildClientTools, CITIZEN_AGENT_ID } from "@/lib/voice";
import { useSession } from "@/lib/runlog";

/** Talk to the twin. Office sessions get the private office agent via a signed URL; everyone else the citizen agent. */
export function VoiceButton() {
  const { tier, auth } = useSession();
  const clientTools = useMemo(() => buildClientTools(), []);
  const [error, setError] = useState<string | null>(null);
  const conversation = useConversation({ clientTools, onError: (m: unknown) => setError(String(m)) });
  const live = conversation.status === "connected" || conversation.status === "connecting";
  // The office agent needs the edge function (a signed-in office user). The demo tier switch alone does not unlock it.
  const office = tier === "office" && !isSampleMode && auth !== null;

  async function start() {
    setError(null);
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      if (office) {
        const res = await proxyFetch("/voice/signed_url", {});
        if (!res.ok) throw new Error(`voice: HTTP ${res.status}`);
        const { signed_url } = (await res.json()) as { signed_url: string };
        await conversation.startSession({ signedUrl: signed_url });
      } else {
        await conversation.startSession({ agentId: CITIZEN_AGENT_ID, connectionType: "websocket" });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        className={live ? "btn" : "btn-ghost"}
        onClick={() => void (live ? conversation.endSession() : start())}
        title={office ? "Office voice assistant (AI)" : "Citizen voice assistant (AI)"}
      >
        {live ? (conversation.isSpeaking ? "🔊 Speaking… (stop)" : "🎙 Listening… (stop)") : `🎙 Voice${office ? " (office)" : ""}`}
      </button>
      {error && (
        <span className="max-w-48 truncate text-xs text-red-700" title={error}>
          {error}
        </span>
      )}
    </div>
  );
}
