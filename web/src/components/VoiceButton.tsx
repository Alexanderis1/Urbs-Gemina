import { useMemo, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import { Mic, Square } from "lucide-react";
import { isSampleMode, proxyFetch } from "@/api/client";
import { buildClientTools, CITIZEN_AGENT_ID } from "@/lib/voice";
import { useSession } from "@/lib/runlog";
import { errorText } from "@/lib/errors";
import { texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    connecting: "Connecting…",
    speaking: "Speaking",
    listening: "Listening",
    office: "Office",
    citizen: "Citizen",
    officeTag: "office",
    title: (who: string) => `${who} voice assistant (AI). It speaks Italian and can move the map.`,
    stop: "Stop",
    button: "Voice assistant",
    unavailable: "Voice assistant not available:",
  },
  it: {
    connecting: "Connessione…",
    speaking: "Sta parlando",
    listening: "Ti ascolta",
    office: "del personale",
    citizen: "per i cittadini",
    officeTag: "personale",
    title: (who: string) => `Assistente vocale ${who} (AI). Parla italiano e può spostare la mappa.`,
    stop: "Ferma",
    button: "Assistente vocale",
    unavailable: "Assistente vocale non disponibile:",
  },
});

/** Five bars that move while the assistant speaks and rest while it listens. */
function Level({ active }: { active: boolean }) {
  return (
    <span className="flex h-4 items-center gap-0.5" aria-hidden="true">
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={`h-full w-0.5 origin-center rounded-full bg-current ${active ? "animate-level" : "scale-y-[0.3]"}`}
          style={{ animationDelay: `${i * 110}ms` }}
        />
      ))}
    </span>
  );
}

/** Talk to the twin. Office sessions get the private office agent via a signed URL; everyone else the citizen agent. */
export function VoiceButton() {
  const t = tr(T);
  const { tier, auth } = useSession();
  const clientTools = useMemo(() => buildClientTools(), []);
  const [error, setError] = useState<string | null>(null);
  const conversation = useConversation({ clientTools, onError: (m: unknown) => setError(String(m)) });
  const connecting = conversation.status === "connecting";
  const live = conversation.status === "connected" || connecting;
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
      setError(errorText(e));
    }
  }

  const state = connecting ? t.connecting : conversation.isSpeaking ? t.speaking : t.listening;
  return (
    <div className="relative flex items-center">
      <button
        className={`inline-flex min-h-9 items-center gap-2 rounded border px-3 text-sm font-semibold transition-colors duration-200 ${
          live ? "border-white bg-white text-chrome" : "border-chrome-line text-chrome-ink hover:border-white hover:bg-chrome-line"
        }`}
        onClick={() => void (live ? conversation.endSession() : start())}
        aria-pressed={live}
        title={t.title(office ? t.office : t.citizen)}
      >
        {live ? (
          <>
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inset-0 animate-pulse-ring rounded-full bg-danger" />
              <span className="relative h-2.5 w-2.5 rounded-full bg-danger" />
            </span>
            <span aria-live="polite">{state}</span>
            <Level active={conversation.isSpeaking} />
            <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
            <span className="sr-only">{t.stop}</span>
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" aria-hidden="true" />
            {t.button}
            {office && <span className="rounded-sm bg-chrome-line px-1 text-2xs uppercase tracking-wider">{t.officeTag}</span>}
          </>
        )}
      </button>
      {error && (
        <div role="alert" className="absolute right-0 top-full z-30 mt-2 w-64 animate-rise-in rounded border border-danger/50 bg-surface p-2 text-xs text-danger shadow-float">
          {t.unavailable} {error}
        </div>
      )}
    </div>
  );
}
