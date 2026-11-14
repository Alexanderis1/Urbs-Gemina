// One round trip to the assistant (the /ask route), shared by every screen that asks the twin.
import { useCallback } from "react";
import { isSampleMode, proxyFetch } from "@/api/client";
import { parseTwinAnswer, type TwinAnswer } from "@/api/twin";
import type { ResolvePlaceResult } from "@/api/types";
import { useSession } from "@/lib/runlog";

/** Returns `ask(shown, body)`: `body` goes to the service; `shown` is the request in words (used in sample mode). */
export function useAskTwin(): (shown: string, body: unknown) => Promise<TwinAnswer> {
  const { run } = useSession();
  return useCallback(
    async (shown: string, body: unknown) => {
      if (isSampleMode) return sampleAnswer(shown);
      const res = await proxyFetch("/ask", body);
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(typeof b.detail === "string" ? b.detail : `HTTP ${res.status}`);
      }
      return parseTwinAnswer(await res.json());

      async function sampleAnswer(q: string): Promise<TwinAnswer> {
        // No language model in sample mode. One real tool call (to the sample tools) shows the trace format.
        const place = await run<ResolvePlaceResult>("resolve_place", { text: q });
        return parseTwinAnswer({
          text: `The assistant is not connected yet, so this is not an answer. It shows how answers will look: sources, run ids, data kinds and map buttons.\nSample place found [run:${place.run_id.slice(0, 12)}]`,
          verified: false,
          run_ids: [place.run_id],
          sources: place.sources.map((s) => s.id),
          data_kinds: place.data_kinds,
          synthetic: true,
          missing: ["orchestrator (agents workstream)"],
          citations: [{ line: 1, kind: "run", ref: place.run_id, cite_mode: "auto" }],
          map_actions: [
            { tool: "fly_to", args: { lon: place.result.lon, lat: place.result.lat, zoom: 15, label: place.result.label ?? q } },
            { tool: "show_layer", args: { layer: "air_quality", visible: true } },
          ],
        });
      }
    },
    [run],
  );
}
