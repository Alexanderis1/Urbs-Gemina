import { texts, tr } from "@/lib/i18n";
import { JobError } from "@/lib/jobs";

// Plain-language text for a failed request, so no screen shows "TypeError: Failed to fetch".

const NETWORK = /failed to fetch|networkerror|load failed|network request failed/i;

export const NETWORK_MESSAGE =
  "The live service did not answer. It may still be starting up, or the run took too long for the connection. " +
  "Try again: finished runs are kept, so a repeat answers sooner.";

const FALLBACK = "Something went wrong. Try again.";

const ERR_TEXT = texts({
  en: {
    network: NETWORK_MESSAGE,
    fallback: FALLBACK,
    job: {
      timeout: "This run is taking longer than expected, so the screen stopped waiting. Try a smaller area, or ask again in a few minutes.",
      lost: "The service lost track of this run (it may have restarted). Ask again.",
      unreachable: "The run was started, but the service could not be reached to collect the result. Check the connection and ask again.",
    },
  },
  it: {
    network:
      "Il servizio live non ha risposto. Potrebbe essere ancora in avvio, oppure l'esecuzione è durata troppo per la connessione. " +
      "Riprova: le esecuzioni finite vengono conservate, quindi una nuova richiesta risponde più in fretta.",
    fallback: "Qualcosa è andato storto. Riprova.",
    job: {
      timeout: "Questa esecuzione sta richiedendo più tempo del previsto e la schermata ha smesso di aspettare. Prova con un'area più piccola o riprova tra qualche minuto.",
      lost: "Il servizio ha perso traccia di questa esecuzione (potrebbe essersi riavviato). Riprova.",
      unreachable: "L'esecuzione è partita, ma non è stato possibile raggiungere il servizio per ritirare il risultato. Controlla la connessione e riprova.",
    },
  },
});

function rawMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return e == null ? "" : String(e);
}

/** True when the browser never got a reply (service asleep, connection cut, request blocked). */
export function isNetworkError(e: unknown): boolean {
  return NETWORK.test(rawMessage(e));
}

/** A message a non-technical reader can act on. */
export function errorText(e: unknown): string {
  if (e instanceof JobError) return tr(ERR_TEXT).job[e.code];
  if (isNetworkError(e)) return tr(ERR_TEXT).network;
  const text = rawMessage(e)
    .replace(/^(?:[A-Z][A-Za-z]*Error|Error):\s*/, "")
    .trim();
  return text || tr(ERR_TEXT).fallback;
}
