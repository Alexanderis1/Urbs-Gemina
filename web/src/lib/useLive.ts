// React side of lib/liveLayer.ts: one question, the saved copy at once, the live data when it arrives.
import { useEffect, useRef, useState } from "react";
import { errorText } from "@/lib/errors";
import { layerStore } from "@/lib/layerStore";
import { watchLive, type LiveState } from "@/lib/liveLayer";

const IDLE: LiveState<never> = { value: null, at: null, phase: "loading", error: null };

const pageVisible = () => typeof document === "undefined" || document.visibilityState === "visible";

function onPageVisible(cb: () => void): () => void {
  const listen = () => document.visibilityState === "visible" && cb();
  document.addEventListener("visibilitychange", listen);
  return () => document.removeEventListener("visibilitychange", listen);
}

/**
 * `key` names the question (lib/liveLayer cacheKey); null = nothing to ask. `load` asks the service.
 * `keep` is false for answers that must not be saved (refusals, layers that may not be stored).
 */
export function useLive<T>(key: string | null, load: () => Promise<T>, opts: { maxAgeMs: number; keep?: (value: T) => boolean }): LiveState<T> & { idle: boolean } {
  const [state, setState] = useState<{ key: string | null; live: LiveState<T> }>({ key: null, live: IDLE });
  // `load` and `keep` are rebuilt on every render; `key` says when the question changed.
  const latest = useRef({ load, keep: opts.keep });
  latest.current = { load, keep: opts.keep };
  const { maxAgeMs } = opts;
  useEffect(() => {
    if (key === null) return;
    return watchLive<T>(
      key,
      () => latest.current.load(),
      { maxAgeMs, store: layerStore, keep: (v) => latest.current.keep?.(v) ?? true, visible: pageVisible, onVisible: onPageVisible, errorText },
      (live) => setState({ key, live }),
    );
  }, [key, maxAgeMs]);
  // An answer for an earlier question is never shown for the new one.
  const live = key !== null && state.key === key ? state.live : IDLE;
  return { ...live, idle: key === null };
}
