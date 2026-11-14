import { describe, expect, it } from "vitest";
import { parseTwinAnswer, buildTwinQuestion } from "@/api/twin";

describe("orchestrator hand-over (TwinQuestion / TwinAnswer)", () => {
  it("never sends a tier from the browser", () => {
    const q = buildTwinQuestion("Is the air good in Prati?", { language: "en", area: "municipio:I", conversationId: "c1" });
    expect(q).not.toHaveProperty("tier");
    expect(q).toMatchObject({ question: "Is the air good in Prati?", language: "en", area: "municipio:I", mode: "question", conversation_id: "c1" });
    // The live /ask rejects unknown fields (no "channel").
    expect(q).not.toHaveProperty("channel");
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

describe("answer citations (WS7 trace)", () => {
  it("keeps valid citations and marks auto ones", async () => {
    const { parseTwinAnswer, citationRows } = await import("@/api/twin");
    const a = parseTwinAnswer({
      text: "Intro\nThe field is 0.4 V/m [run:abc123def456]\nSource line [src:arpa]",
      citations: [
        { line: 1, kind: "run", ref: "abc123def4567890", cite_mode: "auto" },
        { line: 2, kind: "src", ref: "arpa", cite_mode: "explicit" },
        { line: "x", kind: "run", ref: "bad" },
        { line: 3, kind: "other", ref: "r", cite_mode: "explicit" },
      ],
    });
    expect(a.citations).toEqual([
      { line: 1, kind: "run", ref: "abc123def4567890", cite_mode: "auto" },
      { line: 2, kind: "src", ref: "arpa", cite_mode: "explicit" },
    ]);
    const rows = citationRows(a);
    expect(rows).toHaveLength(2);
    expect(rows[0]!.text).toBe("The field is 0.4 V/m");
    expect(rows[0]!.citations[0]!.cite_mode).toBe("auto");
  });

  it("has no citations when the field is missing", async () => {
    const { parseTwinAnswer } = await import("@/api/twin");
    expect(parseTwinAnswer({ text: "hi" }).citations).toEqual([]);
  });
});
