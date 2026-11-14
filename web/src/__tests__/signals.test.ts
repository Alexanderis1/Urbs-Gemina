import { describe, expect, it } from "vitest";
import {
  EMPTY_DRAFT,
  routePath,
  toPlanEvents,
  checkPhoto,
  exifDate,
  nextStep,
  readPhotoMeta,
  toToolReports,
  type GpsFix,
  type StaffReportRow,
} from "@/lib/signals";

/** A minimal big-endian JPEG with an EXIF GPS block: lat/lon in degrees, GPS date and UTC time. */
function jpegWithGps(lat: number, lon: number, day = "2026:11:14", hms: [number, number, number] = [5, 0, 0]): ArrayBuffer {
  const bytes: number[] = [];
  const u16 = (v: number) => bytes.push((v >> 8) & 0xff, v & 0xff);
  const u32 = (v: number) => bytes.push((v >>> 24) & 0xff, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff);
  // TIFF part, offsets relative to its start
  const tiff: number[] = [];
  const t16 = (v: number) => tiff.push((v >> 8) & 0xff, v & 0xff);
  const t32 = (v: number) => tiff.push((v >>> 24) & 0xff, (v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff);
  tiff.push(0x4d, 0x4d); t16(42); t32(8);
  // IFD0 at 8: one entry, GPS pointer -> 26
  t16(1); t16(0x8825); t16(4); t32(1); t32(26); t32(0);
  // GPS IFD at 26: 6 entries (2 + 6*12 + 4 = 78) -> data at 104
  const entries: [number, number, number, number][] = [];
  const data: number[] = [];
  const dataStart = 26 + 2 + 6 * 12 + 4;
  const rat = (vals: number[]) => {
    const off = dataStart + data.length;
    for (const v of vals) {
      const num = Math.round(v * 10000);
      data.push((num >>> 24) & 0xff, (num >> 16) & 0xff, (num >> 8) & 0xff, num & 0xff, 0, 0, 0x27, 0x10);
    }
    return off;
  };
  const toDms = (d: number) => {
    const a = Math.abs(d);
    const deg = Math.floor(a);
    const min = Math.floor((a - deg) * 60);
    return [deg, min, (a - deg - min / 60) * 3600];
  };
  const latOff = rat(toDms(lat));
  const lonOff = rat(toDms(lon));
  const timeOff = rat(hms);
  const dayOff = dataStart + data.length;
  for (const c of day) data.push(c.charCodeAt(0));
  data.push(0);
  const refN = (lat >= 0 ? "N" : "S").charCodeAt(0) << 24;
  const refE = (lon >= 0 ? "E" : "W").charCodeAt(0) << 24;
  entries.push([1, 2, 2, refN], [2, 5, 3, latOff], [3, 2, 2, refE], [4, 5, 3, lonOff], [7, 5, 3, timeOff], [29, 2, 11, dayOff]);
  t16(entries.length);
  for (const [tag, type, count, value] of entries) {
    t16(tag); t16(type); t32(count); t32(value);
  }
  t32(0);
  tiff.push(...data);
  u16(0xffd8);
  u16(0xffe1);
  u16(2 + 6 + tiff.length);
  bytes.push(0x45, 0x78, 0x69, 0x66, 0, 0, ...tiff);
  u16(0xffd9);
  void u32;
  return new Uint8Array(bytes).buffer;
}

const GPS: GpsFix = { lat: 41.896, lon: 12.4823, accuracy_m: 12, at: new Date("2026-11-14T05:10:00Z") };

describe("photo metadata", () => {
  it("reads GPS position and UTC time from EXIF", () => {
    const meta = readPhotoMeta(jpegWithGps(41.896, 12.4823));
    expect(meta.lat).toBeCloseTo(41.896, 4);
    expect(meta.lon).toBeCloseTo(12.4823, 4);
    expect(meta.takenAt?.toISOString()).toBe("2026-11-14T05:00:00.000Z");
  });

  it("returns nothing for a photo without EXIF", () => {
    expect(readPhotoMeta(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]).buffer)).toEqual({ lat: null, lon: null, takenAt: null });
    expect(readPhotoMeta(new Uint8Array([1, 2, 3]).buffer).lat).toBeNull();
  });

  it("parses EXIF dates with and without an offset", () => {
    expect(exifDate("2026:11:14 06:00:00", "+01:00")?.toISOString()).toBe("2026-11-14T05:00:00.000Z");
    expect(exifDate("garbage")).toBeNull();
  });
});

describe("photo vs device GPS", () => {
  const now = new Date("2026-11-14T05:10:00Z");
  it("accepts a photo taken here a few minutes ago", () => {
    const r = checkPhoto({ lat: 41.8962, lon: 12.4825, takenAt: new Date("2026-11-14T05:05:00Z") }, GPS, now);
    expect(r.problems).toEqual([]);
    expect(r.distanceM).toBeLessThan(50);
    expect(r.ageMin).toBe(5);
  });
  it("refuses a photo without GPS, far away or old", () => {
    expect(checkPhoto({ lat: null, lon: null, takenAt: now }, GPS, now).problems).toEqual(["no_gps"]);
    expect(checkPhoto({ lat: 41.95, lon: 12.5, takenAt: now }, GPS, now).problems).toEqual(["too_far"]);
    expect(checkPhoto({ lat: 41.896, lon: 12.4823, takenAt: new Date("2026-11-10T05:00:00Z") }, GPS, now).problems).toEqual(["too_old"]);
  });
});

describe("guided steps", () => {
  it("walks login, category, GPS, photo, text, confirm", () => {
    expect(nextStep(EMPTY_DRAFT, false)).toBe("login");
    expect(nextStep(EMPTY_DRAFT, true)).toBe("category");
    expect(nextStep({ ...EMPTY_DRAFT, category: "flood" }, true)).toBe("category"); // flood or sewer?
    const d1 = { ...EMPTY_DRAFT, category: "flood" as const, subtype: "sewer" };
    expect(nextStep(d1, true)).toBe("gps");
    const d2 = { ...d1, gps: GPS };
    expect(nextStep(d2, true)).toBe("photo");
    const d3 = { ...d2, photo: new Blob(["x"]), photoSource: "camera" as const, photoGpsDistanceM: 0, photoAgeMin: 0 };
    expect(nextStep(d3, true)).toBe("text");
    expect(nextStep({ ...d3, description: "Sottopasso allagato" }, true)).toBe("confirm");
  });
  it("does not accept a device position outside Rome", () => {
    expect(nextStep({ ...EMPTY_DRAFT, category: "pothole", gps: { ...GPS, lat: 45.46, lon: 9.19 } }, true)).toBe("gps");
  });
  it("a public event can skip the photo, a pothole cannot", () => {
    const base = { ...EMPTY_DRAFT, gps: GPS, skipPhoto: true, description: "Concerto in piazza" };
    expect(nextStep({ ...base, category: "public_event" }, true)).toBe("confirm");
    expect(nextStep({ ...base, category: "pothole" }, true)).toBe("photo");
  });
});

describe("staff rows", () => {
  it("become anonymous tool reports and skip dismissed ones", () => {
    const row: StaffReportRow = {
      id: "r1", category: "flood", subtype: "sewer", screen_photo: "consistent", description: "acqua", lon: 12.48, lat: 41.89, photo_path: "u/p.jpg",
      photo_gps_distance_m: 20, photo_age_min: 3, status: "new", created_at: "2026-11-14T05:00:00Z", reporter_key: "k1",
    };
    const out = toToolReports([row, { ...row, id: "r2", status: "dismissed" }]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ id: "r1", reporter: "k1", has_photo: true, photo_gps_distance_m: 20, time: row.created_at });
  });
});

describe("maintenance plan helpers", () => {
  it("sends anonymous events with the confirmed flag and closes each route at its depot", () => {
    const ev = { id: "sig-1", category: "pothole", category_label: "Buca", lon: 12.5, lat: 41.9, confidence: 0.3, scored: true, report_ids: ["r1"], n_reports: 2, texts: ["x"] };
    const [out] = toPlanEvents([ev as never], new Set(["r1"]));
    expect(out).toEqual({ id: "sig-1", category: "pothole", category_label: "Buca", lon: 12.5, lat: 41.9, confidence: 0.3, scored: true, confirmed: true, n_reports: 2 });
    const path = routePath({ crew: "roads-1", crew_type: "roads", depot: "d", depot_lon: 12.4, depot_lat: 41.8, stops: [{ id: "a", kind: "pothole", label: "", lon: 12.5, lat: 41.9, priority: 1, arrive_min: 5 }], km: 1, hours: 1, cost_eur: 1 });
    expect(path[0]).toEqual(path[path.length - 1]);
    expect(path).toHaveLength(3);
  });
});
