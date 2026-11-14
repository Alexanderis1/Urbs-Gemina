// Citizen reports ("segnalazioni"): pure helpers shared by the guided report (public side) and the staff layer.
// Numbers that decide anything (clustering, confidence) are computed by the tool API (signal_events),
// never here. This file only reads the photo's own GPS and time, measures how far they are from the device GPS,
// and prepares the anonymous rows the staff tool needs.

// Report types chosen by Alessandro (14 Nov 2026). Same ids as config/signals.yaml and the edge function.
export const CATEGORIES = ["flood", "pothole", "traffic", "roadworks", "public_event"] as const;
export type Category = (typeof CATEGORIES)[number];

/** What the resident picks inside a type (none = no choice). */
export const SUBTYPES: Record<Category, readonly string[]> = {
  flood: ["flood", "sewer"],
  pothole: [],
  traffic: ["incident", "congestion", "bus", "metro"],
  roadworks: [],
  public_event: [],
};

/** Public events can be sent with a description only. */
export const PHOTO_REQUIRED: Record<Category, boolean> = { flood: true, pothole: true, traffic: true, roadworks: true, public_event: false };

export function isCategory(v: string | null): v is Category {
  return v !== null && (CATEGORIES as readonly string[]).includes(v);
}

export type PhotoSource = "camera" | "gallery";

export interface GpsFix {
  lat: number;
  lon: number;
  accuracy_m: number | null;
  at: Date;
}

export interface PhotoMeta {
  lat: number | null;
  lon: number | null;
  takenAt: Date | null;
}

/** What the browser stores for one report (no name, no e-mail, no raw photo coordinates). */
export interface ReportDraft {
  category: Category | null;
  subtype: string | null;
  /** The resident chose to send without a photo (only where a photo is optional). */
  skipPhoto: boolean;
  description: string;
  gps: GpsFix | null;
  photo: Blob | null;
  photoSource: PhotoSource | null;
  photoGpsDistanceM: number | null;
  photoAgeMin: number | null;
}

export const EMPTY_DRAFT: ReportDraft = {
  category: null,
  subtype: null,
  skipPhoto: false,
  description: "",
  gps: null,
  photo: null,
  photoSource: null,
  photoGpsDistanceM: null,
  photoAgeMin: null,
};

export const MAX_DESCRIPTION = 280;

/** Same limits as config/signals.yaml location_check (the API re-checks them). */
export const PHOTO_MAX_DISTANCE_M = 250;
export const PHOTO_MAX_AGE_MIN = 120;

export function inRome(lat: number, lon: number): boolean {
  return lon >= 12.0 && lon <= 13.1 && lat >= 41.4 && lat <= 42.4;
}

export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const dp = r(lat2 - lat1);
  const dl = r(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(a));
}

export type PhotoProblem = "no_gps" | "no_time" | "too_far" | "too_old";

/** Compares the photo's own GPS and time with the device GPS. A report can be sent only when problems is empty. */
export function checkPhoto(meta: PhotoMeta, gps: GpsFix, now: Date = new Date()): {
  distanceM: number | null;
  ageMin: number | null;
  problems: PhotoProblem[];
} {
  const problems: PhotoProblem[] = [];
  const distance = meta.lat !== null && meta.lon !== null ? distanceM(meta.lat, meta.lon, gps.lat, gps.lon) : null;
  const age = meta.takenAt ? (now.getTime() - meta.takenAt.getTime()) / 60_000 : null;
  if (distance === null) problems.push("no_gps");
  else if (distance > PHOTO_MAX_DISTANCE_M) problems.push("too_far");
  if (age === null) problems.push("no_time");
  else if (age > PHOTO_MAX_AGE_MIN || age < -5) problems.push("too_old");
  return { distanceM: distance === null ? null : Math.round(distance), ageMin: age === null ? null : Math.round(age * 10) / 10, problems };
}

export type DraftStep = "login" | "category" | "gps" | "photo" | "text" | "confirm";

/** The first step that is not complete yet ("confirm" when everything is ready). */
export function nextStep(d: ReportDraft, signedIn: boolean): DraftStep {
  if (!signedIn) return "login";
  if (!d.category || (SUBTYPES[d.category].length > 0 && !(d.subtype && SUBTYPES[d.category].includes(d.subtype)))) return "category";
  if (!d.gps || !inRome(d.gps.lat, d.gps.lon)) return "gps";
  const photoDone = d.photo !== null && d.photoGpsDistanceM !== null && d.photoAgeMin !== null;
  if (!photoDone && (PHOTO_REQUIRED[d.category] || !d.skipPhoto)) return "photo";
  if (d.description.trim().length < 3 || d.description.length > MAX_DESCRIPTION) return "text";
  return "confirm";
}

// ---- EXIF (JPEG) ------------------------------------------------------------------------------------------
// Reads only GPS position and the time the photo was taken. The upload is re-encoded without any metadata.

function exifView(buf: ArrayBuffer): { view: DataView; tiff: number; le: boolean } | null {
  const view = new DataView(buf);
  if (view.byteLength < 4 || view.getUint16(0) !== 0xffd8) return null;
  let off = 2;
  while (off + 4 <= view.byteLength) {
    if (view.getUint8(off) !== 0xff) return null;
    const marker = view.getUint8(off + 1);
    const len = view.getUint16(off + 2);
    if (marker === 0xe1 && off + 10 <= view.byteLength && view.getUint32(off + 4) === 0x45786966) {
      const tiff = off + 10;
      const order = view.getUint16(tiff);
      if (order !== 0x4949 && order !== 0x4d4d) return null;
      return { view, tiff, le: order === 0x4949 };
    }
    if (marker === 0xda) return null; // image data starts: no EXIF
    off += 2 + len;
  }
  return null;
}

type Entry = { type: number; count: number; valueOff: number };

function readIfd(view: DataView, tiff: number, ifd: number, le: boolean): Map<number, Entry> {
  const out = new Map<number, Entry>();
  const start = tiff + ifd;
  if (start + 2 > view.byteLength) return out;
  const n = view.getUint16(start, le);
  for (let i = 0; i < n; i++) {
    const e = start + 2 + i * 12;
    if (e + 12 > view.byteLength) break;
    const type = view.getUint16(e + 2, le);
    const count = view.getUint32(e + 4, le);
    const size = ({ 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 } as Record<number, number>)[type] ?? 1;
    const valueOff = size * count <= 4 ? e + 8 : tiff + view.getUint32(e + 8, le);
    out.set(view.getUint16(e, le), { type, count, valueOff });
  }
  return out;
}

function ascii(view: DataView, e: Entry | undefined): string | null {
  if (!e || e.type !== 2 || e.valueOff + e.count > view.byteLength) return null;
  let s = "";
  for (let i = 0; i < e.count; i++) {
    const c = view.getUint8(e.valueOff + i);
    if (c === 0) break;
    s += String.fromCharCode(c);
  }
  return s;
}

function rationals(view: DataView, e: Entry | undefined, le: boolean): number[] | null {
  if (!e || e.type !== 5 || e.valueOff + 8 * e.count > view.byteLength) return null;
  const out: number[] = [];
  for (let i = 0; i < e.count; i++) {
    const num = view.getUint32(e.valueOff + i * 8, le);
    const den = view.getUint32(e.valueOff + i * 8 + 4, le);
    out.push(den === 0 ? NaN : num / den);
  }
  return out;
}

function dms(parts: number[] | null, ref: string | null, neg: string): number | null {
  if (!parts || parts.length < 3 || parts.some((p) => !Number.isFinite(p))) return null;
  const v = parts[0]! + parts[1]! / 60 + parts[2]! / 3600;
  return ref?.toUpperCase().startsWith(neg) ? -v : v;
}

/** "2026:11:14 06:03:09" (+ optional "+01:00") to a Date. Without an offset it is read as the device's local time. */
export function exifDate(s: string | null, offset: string | null = null): Date | null {
  const m = s ? /^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(s) : null;
  if (!m) return null;
  const iso = `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`;
  const d = new Date(offset && /^[+-]\d{2}:\d{2}$/.test(offset) ? iso + offset : iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function readPhotoMeta(buf: ArrayBuffer): PhotoMeta {
  const empty: PhotoMeta = { lat: null, lon: null, takenAt: null };
  const x = exifView(buf);
  if (!x) return empty;
  const { view, tiff, le } = x;
  try {
    const ifd0 = readIfd(view, tiff, view.getUint32(tiff + 4, le), le);
    let lat: number | null = null;
    let lon: number | null = null;
    let takenAt: Date | null = null;
    const gpsPtr = ifd0.get(0x8825);
    if (gpsPtr) {
      const gps = readIfd(view, tiff, view.getUint32(gpsPtr.valueOff, le), le);
      lat = dms(rationals(view, gps.get(2), le), ascii(view, gps.get(1)), "S");
      lon = dms(rationals(view, gps.get(4), le), ascii(view, gps.get(3)), "W");
      const day = ascii(view, gps.get(29));
      const hms = rationals(view, gps.get(7), le);
      if (day && hms && hms.length >= 3) {
        const pad = (n: number) => String(Math.floor(n)).padStart(2, "0");
        takenAt = exifDate(`${day} ${pad(hms[0]!)}:${pad(hms[1]!)}:${pad(hms[2]!)}`, "+00:00");
      }
    }
    const exifPtr = ifd0.get(0x8769);
    if (!takenAt && exifPtr) {
      const exif = readIfd(view, tiff, view.getUint32(exifPtr.valueOff, le), le);
      takenAt = exifDate(ascii(view, exif.get(0x9003)), ascii(view, exif.get(0x9011)));
    }
    if (!takenAt) takenAt = exifDate(ascii(view, ifd0.get(0x0132)));
    const ok = lat !== null && lon !== null && !(lat === 0 && lon === 0);
    return { lat: ok ? lat : null, lon: ok ? lon : null, takenAt };
  } catch {
    return empty;
  }
}

// ---- Staff side --------------------------------------------------------------------------------------------

/** A row of the citizen_reports_staff view (no user id: reporter_key is a one-way key per account). */
export interface StaffReportRow {
  id: string;
  category: Category;
  subtype: string | null;
  screen_photo: string | null;
  description: string;
  lon: number;
  lat: number;
  photo_path: string | null;
  photo_gps_distance_m: number | null;
  photo_age_min: number | null;
  status: "new" | "confirmed" | "dismissed" | "fixed";
  created_at: string;
  reporter_key: string;
}

/** The anonymous report the signal_events tool takes. Dismissed reports are left out. */
export function toToolReports(rows: StaffReportRow[]): Record<string, unknown>[] {
  return rows
    .filter((r) => r.status !== "dismissed" && r.status !== "fixed")
    .map((r) => ({
      id: r.id,
      category: r.category,
      ...(r.subtype ? { subtype: r.subtype } : {}),
      lon: r.lon,
      lat: r.lat,
      time: r.created_at,
      reporter: r.reporter_key,
      has_photo: Boolean(r.photo_path),
      text: r.description.slice(0, MAX_DESCRIPTION),
      ...(r.photo_path ? { photo_ref: r.photo_path } : {}),
      ...(r.photo_gps_distance_m !== null ? { photo_gps_distance_m: r.photo_gps_distance_m } : {}),
      ...(r.photo_age_min !== null ? { photo_age_min: r.photo_age_min } : {}),
    }));
}

export type Level = "likely" | "probable" | "unconfirmed" | "not_scored";

export interface TwinEvidence {
  layer: string;
  unit?: string | null;
  verdict: "supports" | "contradicts" | "neutral" | "not_available";
  value: number | null;
  lr: number;
  simulated_input: boolean;
  reason?: string;
}

export interface Factor {
  factor: string;
  lr: number | null;
  detail?: string;
  p?: number;
}

export interface SignalEvent {
  id: string;
  category: Category;
  category_label: string;
  scored: boolean;
  subtypes: Record<string, number>;
  lon: number;
  lat: number;
  radius_m: number;
  first_seen: string;
  last_seen: string;
  stale: boolean;
  n_reports: number;
  n_reporters: number;
  n_photos: number;
  n_location_match: number;
  n_location_mismatch: number;
  report_ids: string[];
  photo_refs: string[];
  texts: string[];
  twin: TwinEvidence[];
  checks: { photo?: string; news?: string };
  confidence: number | null;
  level: Level;
  factors: Factor[];
}

export interface SignalEventsResult {
  events: SignalEvent[];
  n_reports: number;
  as_of: string;
}

export interface Verification {
  event_id: string;
  photo: "consistent" | "inconsistent" | "unclear" | "no_photo";
  news: "confirms" | "no_match";
  reason: string;
  news_results: { url: string; title: string; published?: string | null }[];
  photos_checked: number;
}

/** Colour of an event on the map by level: [r, g, b]. */
export function levelColour(level: Level): [number, number, number] {
  if (level === "not_scored") return [0, 112, 127];
  return level === "likely" ? [204, 51, 51] : level === "probable" ? [230, 140, 0] : [120, 130, 145];
}
