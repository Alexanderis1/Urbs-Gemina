import { describe, expect, it } from "vitest";
import { errorText, isNetworkError } from "@/lib/errors";
import { setLang } from "@/lib/i18n";

describe("errorText", () => {
  it("turns a browser network failure into a plain sentence", () => {
    for (const raw of [new TypeError("Failed to fetch"), new TypeError("NetworkError when attempting to fetch resource."), new TypeError("Load failed")]) {
      expect(isNetworkError(raw)).toBe(true);
      const text = errorText(raw);
      expect(text).toMatch(/did not answer/);
      expect(text).not.toMatch(/TypeError|fetch/i);
    }
  });

  it("keeps a server message but drops the error class name", () => {
    expect(errorText(new Error("503 Service Unavailable"))).toBe("503 Service Unavailable");
    expect(errorText("Error: tool refused")).toBe("tool refused");
    expect(isNetworkError(new Error("503"))).toBe(false);
  });

  it("never returns an empty message", () => {
    expect(errorText(undefined)).toBe("Something went wrong. Try again.");
    expect(errorText(new Error(""))).toBe("Something went wrong. Try again.");
  });
});

describe("errorText in Italian", () => {
  it("speaks Italian", () => {
    setLang("it");
    try {
      expect(errorText(new TypeError("Failed to fetch"))).toMatch(/Il servizio live non ha risposto/);
      expect(errorText("")).toBe("Qualcosa è andato storto. Riprova.");
    } finally {
      setLang("en");
    }
  });
});
