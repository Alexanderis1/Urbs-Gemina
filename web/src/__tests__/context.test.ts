import { describe, expect, it } from "vitest";
import { contextRows } from "@/lib/context";
import { setLang } from "@/lib/i18n";

const result = {
  groups: { sensitive_site: { label: "Sites", layers: [{ layer: "schools", label: "Schools", status: "ok", hits: [{ distance_m: 10, name: null }] }] } },
};

describe("context rows", () => {
  it("names an unnamed hit in English", () => {
    expect(contextRows(result)[0]!.name).toBe("(unnamed)");
  });

  it("speaks Italian", () => {
    setLang("it");
    try {
      expect(contextRows(result)[0]!.name).toBe("(senza nome)");
    } finally {
      setLang("en");
    }
  });
});
