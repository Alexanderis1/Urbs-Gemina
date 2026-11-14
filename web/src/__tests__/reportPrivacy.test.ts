import { describe, expect, it } from "vitest";
import { REPORT_LIMITS, redactPersonalData, reportLimit, validateReport } from "../../supabase/functions/_shared/policy";

const USER = "11111111-2222-3333-4444-555555555555";
const base = { category: "pothole", lon: 12.5, lat: 41.9, photo_path: `${USER}/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jpg`,
  photo_gps_distance_m: 10, photo_age_min: 2, photo_source: "camera" };

describe("personal data is removed from the report text before Claude or staff see it", () => {
  it.each([
    ["scrivetemi a mario.rossi@example.it", "mario.rossi@example.it"],
    ["chiamate il 333 123 4567", "333 123 4567"],
    ["tel +39 06-1234567", "+39 06-1234567"],
    ["targa AB123CD parcheggiata sopra", "AB123CD"],
    ["l'auto ab 123 cd ha urtato", "ab 123 cd"],
    ["CF RSSMRA80A01H501U", "RSSMRA80A01H501U"],
    ["IBAN IT60X0542811101000000123456", "IT60X0542811101000000123456"],
  ])("%s", (text, secret) => {
    const out = redactPersonalData(text);
    expect(out).not.toContain(secret);
    expect(out).toContain("[dato rimosso]");
  });

  it("keeps ordinary details: house numbers, times, dates, bus lines", () => {
    const text = "Buca davanti al civico 345 di via Tuscolana, dalle 8:30 del 14/11/2026, linea 64 ferma";
    expect(redactPersonalData(text)).toBe(text);
  });

  it("validateReport stores and screens only the cleaned text", () => {
    const r = validateReport({ ...base, description: "buca enorme, chiamate 3331234567" }, USER);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.row.description).toBe("buca enorme, chiamate [dato rimosso]");
  });
});

describe("each account can send only a few reports per hour and per day", () => {
  it("allows reports under both limits", () => {
    expect(reportLimit(0, 0)).toBeNull();
    expect(reportLimit(REPORT_LIMITS.perHour - 1, REPORT_LIMITS.perDay - 1)).toBeNull();
  });

  it("stops at the hourly and at the daily limit, with an Italian message", () => {
    const hour = reportLimit(REPORT_LIMITS.perHour, 0);
    const day = reportLimit(0, REPORT_LIMITS.perDay);
    expect(hour?.status).toBe(429);
    expect(day?.status).toBe(429);
    expect(day?.detail).toMatch(/oggi/);
    expect(hour?.detail).toMatch(/ora/);
  });

  it("the daily limit is the tighter one over a day", () => {
    expect(REPORT_LIMITS.perDay).toBeLessThanOrEqual(REPORT_LIMITS.perHour * 24);
    expect(REPORT_LIMITS.perHour).toBeLessThanOrEqual(REPORT_LIMITS.perDay);
  });
});
