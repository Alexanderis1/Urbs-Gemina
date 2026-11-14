// Plain-language text for a failed request, so no screen shows "TypeError: Failed to fetch".

const NETWORK = /failed to fetch|networkerror|load failed|network request failed/i;

export const NETWORK_MESSAGE =
  "The live service did not answer. It may still be starting up, or the run took too long for the connection. " +
  "Try again: finished runs are kept, so a repeat answers sooner.";

const FALLBACK = "Something went wrong. Try again.";

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
  if (isNetworkError(e)) return NETWORK_MESSAGE;
  const text = rawMessage(e)
    .replace(/^(?:[A-Z][A-Za-z]*Error|Error):\s*/, "")
    .trim();
  return text || FALLBACK;
}
