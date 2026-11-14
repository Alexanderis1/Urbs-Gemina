import { describe, expect, it } from "vitest";
import { micProblem } from "@/lib/voice";

function named(name: string, message: string) {
  const e = new Error(message);
  e.name = name;
  return e;
}

describe("micProblem", () => {
  it("spots a blocked microphone", () => {
    expect(micProblem(named("NotAllowedError", "Permission denied"))).toBe("denied");
    expect(micProblem("Permission denied")).toBe("denied");
  });
  it("spots a missing microphone", () => {
    expect(micProblem(named("NotFoundError", "Requested device not found"))).toBe("missing");
  });
  it("leaves other errors alone", () => {
    expect(micProblem(new Error("voice: HTTP 500"))).toBeNull();
  });
});
