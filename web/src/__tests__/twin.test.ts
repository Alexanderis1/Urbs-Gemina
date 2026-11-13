import { describe, expect, it } from "vitest";
import { parseTwinAnswer, buildTwinQuestion } from "@/api/twin";

describe("orchestrator hand-over (TwinQuestion / TwinAnswer)", () => {
  it("never sends a tier from the browser", () => {
    const q = buildTwinQuestion("Is the air good in Prati?", { language: "en", area: "municipio:I", conversationId: "c1" });
    expect(q).not.toHaveProperty("tier");
    expect(q).toMatchObject({ question: "Is the air good in Prati?", language: "en", area: "municipio:I", mode: "question", conversation_id: "c1" });
  });

  it("fails safe: unverified and synthetic unless stated", () => {
    const a = parseTwinAnswer({ text: "hello" });
    expect(a.verified).toBe(false);
    expect(a.synthetic).toBe(true);
    expect(a.run_ids).toEqual([]);
  });

  it("parses a full answer and filters bad map actions", () => {
    const a = parseTwinAnswer({
      text: "ok",
      verified: true,
      run_ids: ["abc"],
      sources: ["roma_wfs"],
      data_kinds: { schools: "real", bogus: "maybe" },
      synthetic: false,
      missing: [],
      map_actions: [{ tool: "fly_to", args: { lon: 12.5, lat: 41.9 } }, { tool: "fly_to", args: { lon: 0, lat: 0 } }],
    });
    expect(a.verified).toBe(true);
    expect(a.synthetic).toBe(false);
    expect(a.data_kinds).toEqual({ schools: "real" });
    expect(a.map_actions).toHaveLength(1);
  });
});
