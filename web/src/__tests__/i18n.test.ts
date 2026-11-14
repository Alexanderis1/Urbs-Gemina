import { afterEach, describe, expect, it } from "vitest";
import { getLang, locale, resolveLang, setLang, texts, tr } from "@/lib/i18n";

afterEach(() => setLang("en")); // the rest of the suite reads English (see setup.ts)

describe("language", () => {
  it("is Italian first: anything but a stored 'en' gives Italian", () => {
    expect(resolveLang(null)).toBe("it");
    expect(resolveLang("it")).toBe("it");
    expect(resolveLang("en")).toBe("en");
    expect(resolveLang("fr")).toBe("it");
  });

  it("picks the text of the current language, also for texts with values in them", () => {
    const T = texts({
      en: { title: "City view", cells: (n: number) => `${n} cells` },
      it: { title: "Vista città", cells: (n: number) => `${n} celle` },
    });
    setLang("it");
    expect(getLang()).toBe("it");
    expect(tr(T).title).toBe("Vista città");
    expect(tr(T).cells(3)).toBe("3 celle");
    setLang("en");
    expect(tr(T).title).toBe("City view");
  });

  it("writes numbers the way the language does", () => {
    setLang("it");
    expect(locale()).toBe("it-IT");
    expect((12345.5).toLocaleString(locale())).toBe("12.345,5");
    setLang("en");
    expect(locale()).toBe("en-GB");
  });
});
