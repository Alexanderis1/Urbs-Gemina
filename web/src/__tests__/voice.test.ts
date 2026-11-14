import { describe, expect, it } from "vitest";
import { buildClientTools, VOICE_TOOL_NAMES, CITIZEN_AGENT_ID } from "@/lib/voice";

describe("voice client tools", () => {
  it("registers exactly the five shared map tools", () => {
    const tools = buildClientTools(() => true);
    expect(Object.keys(tools).sort()).toEqual([...VOICE_TOOL_NAMES].sort());
  });
  it("passes the voice model's arguments to the map unchanged", () => {
    const seen: unknown[] = [];
    const tools = buildClientTools((a) => (seen.push(a), true));
    tools.fly_to!({ lon: 12.49, lat: 41.89, zoom: 16 });
    expect(seen).toEqual([{ tool: "fly_to", args: { lon: 12.49, lat: 41.89, zoom: 16 } }]);
  });
  it("uses the public citizen agent id", () => {
    expect(CITIZEN_AGENT_ID).toBe("agent_1501m7b8c0zpfxm9r3wq8cg1sz9b");
  });
});
