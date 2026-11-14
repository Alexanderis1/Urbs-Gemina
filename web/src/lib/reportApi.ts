// Browser side of citizen reports: device GPS, photo re-encoding without metadata, Lovable Cloud storage,
// and the two staff tools (signal_events, verify_signal) through the "tools" edge function.
import { parseEnvelope } from "@/api/envelope";
import { proxyFetch } from "@/api/client";
import type { Envelope } from "@/api/types";
import { supabase } from "@/integrations/supabase/client";
import { callWithWakeUp } from "@/lib/retry";
import sample from "@/api/sampleSignals.json";
import {
  readPhotoMeta,
  toToolReports,
  type GpsFix,
  type PhotoMeta,
  type ReportDraft,
  type SignalEvent,
  type SignalEventsResult,
  type StaffReportRow,
  type Verification,
} from "@/lib/signals";

export const PHOTO_BUCKET = "report-photos";
const MAX_SIDE = 1600;
const LOCAL_KEY = "urbs.demoReports";

/** True when reports really go to Lovable Cloud; false in the demo build without it (nothing leaves the browser). */
export const reportsLive = supabase !== null;

export type GpsError = "unsupported" | "denied" | "unavailable" | "timeout";

export function getDeviceGps(): Promise<GpsFix> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject("unsupported" satisfies GpsError);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy ?? null, at: new Date(p.timestamp) }),
      (e) => reject((e.code === 1 ? "denied" : e.code === 3 ? "timeout" : "unavailable") satisfies GpsError),
      { enableHighAccuracy: true, timeout: 20_000, maximumAge: 30_000 },
    );
  });
}

export async function photoMetaOf(file: Blob): Promise<PhotoMeta> {
  return readPhotoMeta(await file.arrayBuffer());
}

/** Draws the image on a canvas and saves a new JPEG: every EXIF field (GPS, device, owner) is dropped. */
export async function reencodeWithoutMetadata(source: Blob | HTMLVideoElement): Promise<Blob> {
  let w: number;
  let h: number;
  let draw: (ctx: CanvasRenderingContext2D, cw: number, ch: number) => void;
  if (source instanceof Blob) {
    const bmp = await createImageBitmap(source, { imageOrientation: "from-image" });
    w = bmp.width;
    h = bmp.height;
    draw = (ctx, cw, ch) => ctx.drawImage(bmp, 0, 0, cw, ch);
  } else {
    w = source.videoWidth;
    h = source.videoHeight;
    draw = (ctx, cw, ch) => ctx.drawImage(source, 0, 0, cw, ch);
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas not available");
  draw(ctx, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode failed"))), "image/jpeg", 0.85));
}

// ---- Demo SPID ----------------------------------------------------------------------------------------------
// Real SPID needs AgID accreditation of the service provider. This button is a clearly marked simulation:
// with Lovable Cloud it opens an anonymous account (one per browser), without it a local demo session.

export async function demoSpidSignIn(): Promise<{ ok: true } | { ok: false; reason: string }> {
  if (!supabase) {
    try {
      window.sessionStorage.setItem("urbs.demoSpid", "1");
    } catch {
      // the session still holds in memory
    }
    return { ok: true };
  }
  const { error } = await supabase.auth.signInAnonymously();
  return error ? { ok: false, reason: error.message } : { ok: true };
}

export function demoLocalSignedIn(): boolean {
  try {
    return window.sessionStorage.getItem("urbs.demoSpid") === "1";
  } catch {
    return false;
  }
}

// ---- Sending ------------------------------------------------------------------------------------------------

export async function submitReport(d: ReportDraft): Promise<{ id: string; live: boolean }> {
  if (!d.category || !d.gps || !d.photo || !d.photoSource || d.photoGpsDistanceM === null || d.photoAgeMin === null)
    throw new Error("incomplete report");
  const row = {
    category: d.category,
    description: d.description.trim(),
    lon: d.gps.lon,
    lat: d.gps.lat,
    gps_accuracy_m: d.gps.accuracy_m,
    photo_source: d.photoSource,
    photo_gps_distance_m: d.photoGpsDistanceM,
    photo_age_min: d.photoAgeMin,
  };
  if (!supabase) {
    const id = crypto.randomUUID();
    const kept = readLocal();
    kept.push({ ...row, id, created_at: new Date().toISOString() });
    try {
      window.localStorage.setItem(LOCAL_KEY, JSON.stringify(kept.slice(-20)));
    } catch {
      // demo only
    }
    return { id, live: false };
  }
  const { data: u } = await supabase.auth.getUser();
  if (!u.user) throw new Error("not signed in");
  const path = `${u.user.id}/${crypto.randomUUID()}.jpg`;
  const up = await supabase.storage.from(PHOTO_BUCKET).upload(path, d.photo, { contentType: "image/jpeg", upsert: false });
  if (up.error) throw new Error(up.error.message);
  const { data, error } = await supabase.from("citizen_reports").insert({ ...row, photo_path: path }).select("id").single();
  if (error) throw new Error(error.message);
  return { id: String((data as { id: string }).id), live: true };
}

function readLocal(): Record<string, unknown>[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(LOCAL_KEY) ?? "[]") as unknown;
    return Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
  } catch {
    return [];
  }
}

// ---- Staff --------------------------------------------------------------------------------------------------

export async function loadStaffReports(): Promise<StaffReportRow[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from("citizen_reports_staff")
    .select("id,category,description,lon,lat,photo_path,photo_gps_distance_m,photo_age_min,status,created_at,reporter_key")
    .order("created_at", { ascending: false })
    .limit(2000);
  if (error) throw new Error(error.message);
  return (data ?? []) as StaffReportRow[];
}

async function postTool<R>(tool: string, body: Record<string, unknown>): Promise<Envelope<R>> {
  const once = async () => {
    const res = await proxyFetch(`/tools/${tool}`, body);
    if (!res.ok) {
      const b = (await res.json().catch(() => ({}))) as { detail?: unknown };
      throw new Error(`${tool}: ${typeof b.detail === "string" ? b.detail : `HTTP ${res.status}`}`);
    }
    return parseEnvelope(await res.json()) as Envelope<R>;
  };
  return callWithWakeUp(once, async () => void (await proxyFetch("/tools/data_status", {})));
}

export type Checks = Record<string, { photo?: string; news?: string }>;

/** Events from the reports. Without Lovable Cloud: a fixed sample computed by the same tool (labelled SAMPLE). */
export async function runSignalEvents(rows: StaffReportRow[], checks: Checks): Promise<{ result: SignalEventsResult; env: Envelope | null; sample: boolean }> {
  if (!supabase) return { result: sample as unknown as SignalEventsResult, env: null, sample: true };
  const env = await postTool<SignalEventsResult>("signal_events", { reports: toToolReports(rows), check_twin: true, checks });
  if ((env.status ?? "ok") !== "ok") throw new Error(env.reason ?? "signal_events not available");
  return { result: env.result as SignalEventsResult, env: env as Envelope, sample: false };
}

export async function photoUrls(paths: string[], seconds = 600): Promise<string[]> {
  if (!supabase || paths.length === 0) return [];
  const { data, error } = await supabase.storage.from(PHOTO_BUCKET).createSignedUrls(paths, seconds);
  if (error) return [];
  return (data ?? []).map((d) => d.signedUrl).filter((u): u is string => Boolean(u));
}

export async function verifyEvent(e: SignalEvent, place: string | null, urls: string[]): Promise<Verification> {
  const env = await postTool<Verification>("verify_signal", {
    event: { id: e.id, category: e.category, category_label: e.category_label, lon: e.lon, lat: e.lat, first_seen: e.first_seen, texts: e.texts.slice(0, 20) },
    ...(place ? { place } : {}),
    photo_urls: urls.slice(0, 6),
  });
  if ((env.status ?? "ok") !== "ok") throw new Error(env.reason ?? "verify_signal not available");
  return env.result as Verification;
}

export async function setReportsStatus(ids: string[], status: "confirmed" | "dismissed"): Promise<void> {
  if (!supabase) return;
  for (const id of ids) {
    const { error } = await supabase.rpc("set_report_status", { report_id: id, new_status: status });
    if (error) throw new Error(error.message);
  }
}
