import { describe, expect, it } from "vitest";
import { conversationCallbacks } from "@/lib/voice";

describe("conversationCallbacks", () => {
  it("passes a function for every callback the ElevenLabs client calls", () => {
    const cb = conversationCallbacks(() => {});
    for (const name of ["onConnect", "onDisconnect", "onMessage", "onAudio", "onDebug", "onUnhandledClientToolCall", "onError"] as const) {
      expect(typeof cb[name]).toBe("function");
    }
  });

  it("forwards errors as text", () => {
    let got = "";
    conversationCallbacks((m) => (got = m)).onError("boom");
    expect(got).toBe("boom");
  });
});
