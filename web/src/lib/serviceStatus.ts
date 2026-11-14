// Whether the live service is answering. Set by the API client, read by the status bar and the wake-up notice.

import { useSyncExternalStore } from "react";

/** "waking": no answer yet, the service is starting. "working": it answered that a long run is in progress. */
export type ServiceStatus = "unknown" | "waking" | "working" | "ready";

let status: ServiceStatus = "unknown";
const listeners = new Set<() => void>();

export function setServiceStatus(next: ServiceStatus): void {
  if (next === status) return;
  status = next;
  for (const l of listeners) l();
}

export function getServiceStatus(): ServiceStatus {
  return status;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

export function useServiceStatus(): ServiceStatus {
  return useSyncExternalStore(subscribe, getServiceStatus, getServiceStatus);
}
