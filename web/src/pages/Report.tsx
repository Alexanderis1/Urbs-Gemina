import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Camera, Car, CheckCircle2, CircleSlash, Construction, ImagePlus, LocateFixed, MapPin, PartyPopper, ShieldAlert, TriangleAlert, Waves, type LucideIcon } from "lucide-react";
import { Callout, Spinner } from "@/components/ui";
import { texts, tr } from "@/lib/i18n";
import { useSession } from "@/lib/runlog";
import { supabase } from "@/integrations/supabase/client";
import {
  CATEGORIES,
  EMPTY_DRAFT,
  PHOTO_REQUIRED,
  SUBTYPES,
  isCategory,
  MAX_DESCRIPTION,
  PHOTO_MAX_AGE_MIN,
  PHOTO_MAX_DISTANCE_M,
  checkPhoto,
  nextStep,
  type Category,
  type DraftStep,
  type PhotoProblem,
  type ReportDraft,
} from "@/lib/signals";
import { demoLocalSignedIn, demoSpidSignIn, getDeviceGps, photoMetaOf, reencodeWithoutMetadata, submitReport, type GpsError, type SubmitResult } from "@/lib/reportApi";

const IT = {
  kicker: "Segnalazioni dei cittadini",
  stepsLabel: "Passaggi",
  title: "Segnala un evento in città",
  lead: "Allagamenti, buche, incidenti, cantieri, eventi: la tua segnalazione aiuta il Comune a capire cosa succede, dove e quando.",
  steps: { login: "Accesso", category: "Cosa succede", gps: "Posizione", photo: "Foto", text: "Descrizione", confirm: "Invio" } as Record<DraftStep, string>,
  spid: "Entra con SPID",
  spidDemo: "SPID simulato per la dimostrazione",
  spidNote:
    "Il vero SPID richiede l'accreditamento del Comune presso AgID. Qui l'accesso è simulato: si apre un account anonimo, senza nome, e-mail o codice fiscale.",
  spidFailed: "Accesso non riuscito",
  category: "Che cosa sta succedendo?",
  cats: {
    flood: ["Allagamento o fogna", "Strada allagata, tombino o fogna che non scarica"],
    pothole: ["Buca in strada", "Buca o avvallamento sull'asfalto"],
    traffic: ["Traffico e trasporti", "Incidente, traffico bloccato, problema bus o metro"],
    roadworks: ["Cantiere non in mappa", "Un cantiere che la mappa non mostra"],
    public_event: ["Evento pubblico", "Un evento aperto a tutti non ancora in mappa"],
  } as Record<Category, [string, string]>,
  subtypeTitle: "Di che cosa si tratta?",
  subtypes: { flood: "Allagamento", sewer: "Fogna o tombino", incident: "Incidente stradale", congestion: "Traffico bloccato", bus: "Problema bus", metro: "Problema metro" } as Record<string, string>,
  skipPhoto: "Invia senza foto",
  photoOptional: "Per un evento pubblico la foto è facoltativa.",
  noPhoto: "Nessuna foto",
  review: "Ricevuta: la sala operativa la controllerà.",
  rejected: "Segnalazione non accettata",
  rejectedLead: "Il controllo automatico l'ha scartata. Se pensi sia un errore, riprova con una foto più chiara e una descrizione precisa.",
  reasons: {
    inappropriate: "contenuto inappropriato", offensive: "linguaggio offensivo", personal_data: "contiene dati personali di altre persone (volti, targhe, nomi)",
    off_topic: "non riguarda la città", not_matching_category: "foto o testo non corrispondono al tipo scelto", likely_false: "sembra non veritiera",
    spam: "pubblicità o spam", injection_attempt: "il testo contiene istruzioni rivolte al sistema",
  } as Record<string, string>,
  screened: "Ogni segnalazione viene controllata da un assistente automatico prima di essere registrata: testo e foto sono trattati come dati, mai come istruzioni.",
  gpsTitle: "Attiva la posizione del telefono",
  gpsLead: "La segnalazione usa la posizione GPS del dispositivo: senza GPS non può essere inviata.",
  gpsButton: "Usa la mia posizione",
  gpsOk: (acc: string) => `Posizione rilevata (precisione circa ${acc} m)`,
  gpsErr: {
    denied: "Hai negato l'accesso alla posizione. Apri le impostazioni del browser, consenti la posizione per questo sito e riprova.",
    unsupported: "Questo browser non fornisce la posizione. Prova con un altro browser del telefono.",
    unavailable: "Posizione non disponibile. Attiva il GPS (Localizzazione) nelle impostazioni del telefono e riprova all'aperto.",
    timeout: "Il GPS non ha risposto in tempo. Riprova all'aperto.",
  } as Record<GpsError, string>,
  gpsOutside: "La posizione è fuori dal territorio di Roma: puoi segnalare solo eventi a Roma.",
  photoTitle: "Fotografa l'evento",
  photoLead: `La foto deve avere la posizione GPS e l'ora dello scatto, entro ${PHOTO_MAX_DISTANCE_M} m da te e da meno di ${PHOTO_MAX_AGE_MIN} minuti.`,
  shoot: "Scatta ora",
  gallery: "Scegli dalla galleria",
  snap: "Scatta",
  cancel: "Annulla",
  cameraErr: "Fotocamera non disponibile. Consenti l'accesso alla fotocamera o scegli una foto dalla galleria.",
  problems: {
    no_gps: "La foto non contiene la posizione. Attiva la geolocalizzazione nella fotocamera (Android: Impostazioni fotocamera › Tag posizione; iPhone: nella scelta della foto tocca Opzioni › Posizione) oppure usa «Scatta ora».",
    no_time: "La foto non contiene l'ora dello scatto. Usa «Scatta ora».",
    too_far: `La foto è stata scattata a più di ${PHOTO_MAX_DISTANCE_M} m da dove ti trovi.`,
    too_old: `La foto è stata scattata più di ${PHOTO_MAX_AGE_MIN} minuti fa: serve una foto dell'evento in corso.`,
  } as Record<PhotoProblem, string>,
  photoOk: (d: number, a: number) => `Foto verificata: scattata a ${d} m da te, ${a} min fa.`,
  privacy: "Prima dell'invio la foto viene ricodificata: tutti i metadati (modello del telefono, coordinate esatte) vengono eliminati.",
  textTitle: "Descrivi in breve",
  textPh: "Es. Sottopasso allagato, le auto non passano",
  textCount: (n: number) => `${n}/${MAX_DESCRIPTION}`,
  confirmTitle: "Controlla e invia",
  send: "Invia la segnalazione",
  sent: "Segnalazione inviata. Grazie!",
  sentLead: "La sala operativa la unisce alle altre segnalazioni vicine e ai dati del gemello digitale per capire se è un evento in corso. In caso di pericolo immediato chiama il 112.",
  sentDemo: "Versione dimostrativa senza Lovable Cloud: la segnalazione è rimasta in questo browser e non è stata inviata.",
  another: "Nuova segnalazione",
  back: "Indietro",
  next: "Avanti",
  emergency: "Pericolo immediato? Chiama il 112. Questa segnalazione non sostituisce i numeri di emergenza.",
  anonymous: "La sala operativa non vede chi ha segnalato: vede solo luogo, ora, categoria, foto e testo.",
};

const EN: typeof IT = {
  kicker: "Citizen reports",
  stepsLabel: "Steps",
  title: "Report an event in the city",
  lead: "Flooding, potholes, accidents, worksites, events: your report helps the city understand what is happening, where and when.",
  steps: { login: "Sign in", category: "What", gps: "Location", photo: "Photo", text: "Description", confirm: "Send" },
  spid: "Sign in with SPID",
  spidDemo: "Simulated SPID for the demo",
  spidNote: "Real SPID needs the city to be accredited by AgID. Here sign-in is simulated: an anonymous account opens, with no name, e-mail or tax code.",
  spidFailed: "Sign-in failed",
  category: "What is happening?",
  cats: {
    flood: ["Flooding or sewer", "Flooded street, drain or sewer not draining"],
    pothole: ["Pothole", "Hole or dip in the road surface"],
    traffic: ["Traffic and transport", "Accident, blocked traffic, bus or metro problem"],
    roadworks: ["Worksite not on the map", "A worksite the map does not show"],
    public_event: ["Public event", "An event open to all, not on the map yet"],
  },
  subtypeTitle: "What is it exactly?",
  subtypes: { flood: "Flooding", sewer: "Sewer or drain", incident: "Road accident", congestion: "Blocked traffic", bus: "Bus problem", metro: "Metro problem" },
  skipPhoto: "Send without a photo",
  photoOptional: "For a public event the photo is optional.",
  noPhoto: "No photo",
  review: "Received: the operations room will check it.",
  rejected: "Report not accepted",
  rejectedLead: "The automatic check discarded it. If you think this is a mistake, try again with a clearer photo and a precise description.",
  reasons: {
    inappropriate: "inappropriate content", offensive: "offensive language", personal_data: "contains other people's personal data (faces, plates, names)",
    off_topic: "not about the city", not_matching_category: "photo or text do not match the chosen type", likely_false: "looks untrue",
    spam: "advertising or spam", injection_attempt: "the text contains instructions aimed at the system",
  },
  screened: "Every report is checked by an automatic assistant before it is recorded: text and photo are treated as data, never as instructions.",
  gpsTitle: "Turn on your phone's location",
  gpsLead: "The report uses the device GPS position: without GPS it cannot be sent.",
  gpsButton: "Use my location",
  gpsOk: (acc: string) => `Location found (accuracy about ${acc} m)`,
  gpsErr: {
    denied: "You denied access to your location. Open the browser settings, allow location for this site and try again.",
    unsupported: "This browser does not give a location. Try another browser on your phone.",
    unavailable: "Location not available. Turn on GPS (Location) in the phone settings and try again outdoors.",
    timeout: "GPS did not answer in time. Try again outdoors.",
  },
  gpsOutside: "The location is outside Rome: you can only report events in Rome.",
  photoTitle: "Take a photo of the event",
  photoLead: `The photo must carry its GPS position and time, within ${PHOTO_MAX_DISTANCE_M} m of you and less than ${PHOTO_MAX_AGE_MIN} minutes old.`,
  shoot: "Take a photo now",
  gallery: "Choose from gallery",
  snap: "Shoot",
  cancel: "Cancel",
  cameraErr: "Camera not available. Allow camera access or choose a photo from the gallery.",
  problems: {
    no_gps: "The photo has no location. Turn on location tags in the camera (Android: camera settings > Location tags; iPhone: when choosing the photo tap Options > Location) or use \u201cTake a photo now\u201d.",
    no_time: "The photo has no time of shooting. Use \u201cTake a photo now\u201d.",
    too_far: `The photo was taken more than ${PHOTO_MAX_DISTANCE_M} m from where you are.`,
    too_old: `The photo was taken more than ${PHOTO_MAX_AGE_MIN} minutes ago: a photo of the event as it happens is needed.`,
  },
  photoOk: (d: number, a: number) => `Photo checked: taken ${d} m from you, ${a} min ago.`,
  privacy: "Before sending, the photo is re-encoded: all metadata (phone model, exact coordinates) is removed.",
  textTitle: "Describe it briefly",
  textPh: "E.g. Flooded underpass, cars cannot pass",
  textCount: (n: number) => `${n}/${MAX_DESCRIPTION}`,
  confirmTitle: "Check and send",
  send: "Send the report",
  sent: "Report sent. Thank you!",
  sentLead: "The operations room merges it with nearby reports and the digital twin's data to see whether an event is under way. In immediate danger call 112.",
  sentDemo: "Demo build without Lovable Cloud: the report stayed in this browser and was not sent.",
  another: "New report",
  back: "Back",
  next: "Next",
  emergency: "Immediate danger? Call 112. This report does not replace the emergency numbers.",
  anonymous: "The operations room does not see who reported: only place, time, category, photo and text.",
};

const T = texts({ it: IT, en: EN });

const ICON: Record<Category, LucideIcon> = { flood: Waves, pothole: TriangleAlert, traffic: Car, roadworks: Construction, public_event: PartyPopper };
const ORDER: DraftStep[] = ["login", "category", "gps", "photo", "text", "confirm"];

function useText() {
  return tr(T);
}

/** Guided report for residents: sign in (demo SPID), category, device GPS, photo with matching GPS, text, send. */
export default function Report() {
  const t = useText();
  const { auth } = useSession();
  const [localSignedIn, setLocalSignedIn] = useState(demoLocalSignedIn);
  const signedIn = supabase ? auth !== null : localSignedIn;
  // The citizen menu links straight to a type: /segnala?tipo=pothole
  const [params] = useSearchParams();
  const preset = params.get("tipo");
  const fresh = (): ReportDraft => ({ ...EMPTY_DRAFT, category: isCategory(preset) ? preset : null });
  const [draft, setDraft] = useState<ReportDraft>(fresh);
  const [view, setView] = useState<DraftStep | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<SubmitResult | null>(null);
  const due = nextStep(draft, signedIn);
  // The resident can go back to a done step; never forward past the first incomplete one.
  const step = view && ORDER.indexOf(view) <= ORDER.indexOf(due) ? view : due;
  const set = (patch: Partial<ReportDraft>) => {
    setError(null);
    setDraft((d) => ({ ...d, ...patch }));
  };
  const go = (s: DraftStep) => {
    setError(null);
    setView(s);
  };

  if (sent) {
    const rejected = sent.verdict === "reject";
    return (
      <Shell t={t}>
        <div className="card space-y-3 text-center">
          {rejected ? (
            <CircleSlash className="mx-auto h-10 w-10 text-danger" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="mx-auto h-10 w-10 text-real" aria-hidden="true" />
          )}
          <h2 className="text-xl font-bold">{rejected ? t.rejected : t.sent}</h2>
          <p className="text-sm text-muted">{rejected ? t.rejectedLead : t.sentLead}</p>
          {rejected && sent.reasons.length > 0 && (
            <ul className="text-left text-sm">
              {sent.reasons.map((r) => <li key={r}>• {t.reasons[r] ?? r}</li>)}
            </ul>
          )}
          {sent.verdict === "review" && <Callout tone="info">{t.review}</Callout>}
          {!sent.live && <Callout tone="warn">{t.sentDemo}</Callout>}
          <button className="btn" onClick={() => { setDraft(fresh()); setView(null); setSent(null); }}>{t.another}</button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell t={t}>
      <ol className="flex flex-wrap gap-1.5" aria-label={t.stepsLabel}>
        {ORDER.map((s, i) => {
          const reachable = ORDER.indexOf(s) <= ORDER.indexOf(due);
          return (
            <li key={s}>
              <button
                disabled={!reachable || s === "login"}
                onClick={() => go(s)}
                aria-current={s === step ? "step" : undefined}
                className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${s === step ? "border-link bg-primary-soft text-link" : reachable ? "border-line-strong text-ink" : "border-line text-muted"}`}
              >
                {i + 1}. {t.steps[s]}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="card space-y-4">
        {step === "login" && <LoginStep t={t} onDone={() => setLocalSignedIn(true)} />}
        {step === "category" && (
          <fieldset className="space-y-3">
            <legend className="text-lg font-bold">{t.category}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {CATEGORIES.map((c) => {
                const Icon = ICON[c];
                const [name, hint] = t.cats[c];
                const on = draft.category === c;
                return (
                  <button
                    key={c}
                    onClick={() => { set({ category: c, subtype: null, skipPhoto: false }); setView(null); }}
                    aria-pressed={on}
                    className={`flex items-start gap-3 rounded border p-3 text-left transition-colors ${on ? "border-link bg-primary-soft" : "border-line-strong hover:border-link"}`}
                  >
                    <Icon className="mt-0.5 h-5 w-5 shrink-0 text-link" aria-hidden="true" />
                    <span>
                      <span className="block font-semibold">{name}</span>
                      <span className="block text-xs text-muted">{hint}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {draft.category && SUBTYPES[draft.category].length > 0 && (
              <div className="space-y-2 pt-1">
                <div className="font-semibold">{t.subtypeTitle}</div>
                <div className="flex flex-wrap gap-2">
                  {SUBTYPES[draft.category].map((st) => (
                    <button
                      key={st}
                      aria-pressed={draft.subtype === st}
                      onClick={() => { set({ subtype: st }); setView(null); }}
                      className={`min-h-11 rounded-full border px-4 text-sm font-semibold ${draft.subtype === st ? "border-link bg-primary-soft text-link" : "border-line-strong hover:border-link"}`}
                    >
                      {t.subtypes[st] ?? st}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </fieldset>
        )}
        {step === "gps" && (
          <GpsStep t={t} draft={draft} onFix={(gps) => { set({ gps, photo: null, photoSource: null, photoGpsDistanceM: null, photoAgeMin: null }); setView(null); }} />
        )}
        {step === "photo" && draft.gps && (
          <PhotoStep
            t={t}
            draft={draft}
            onPhoto={(p) => { set({ ...p, skipPhoto: false }); setView(null); }}
            onSkip={draft.category && !PHOTO_REQUIRED[draft.category] ? () => { set({ skipPhoto: true }); setView(null); } : undefined}
          />
        )}
        {step === "text" && (
          <div className="space-y-2">
            <label htmlFor="report-text" className="text-lg font-bold">{t.textTitle}</label>
            <textarea
              id="report-text"
              className="input min-h-24"
              maxLength={MAX_DESCRIPTION}
              placeholder={t.textPh}
              value={draft.description}
              onChange={(e) => set({ description: e.target.value })}
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted">{t.textCount(draft.description.length)}</span>
              <button className="btn" disabled={draft.description.trim().length < 3} onClick={() => go("confirm")}>{t.next}</button>
            </div>
          </div>
        )}
        {step === "confirm" && draft.category && draft.gps && (
          <div className="space-y-3">
            <h2 className="text-lg font-bold">{t.confirmTitle}</h2>
            <PhotoPreview blob={draft.photo} />
            <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted">{t.steps.category}</dt>
              <dd className="font-semibold">{t.cats[draft.category][0]}{draft.subtype ? ` · ${t.subtypes[draft.subtype] ?? draft.subtype}` : ""}</dd>
              <dt className="text-muted">{t.steps.gps}</dt>
              <dd>{draft.gps.lat.toFixed(5)}, {draft.gps.lon.toFixed(5)}</dd>
              <dt className="text-muted">{t.steps.photo}</dt>
              <dd>{draft.photo && draft.photoGpsDistanceM !== null ? t.photoOk(draft.photoGpsDistanceM, draft.photoAgeMin ?? 0) : t.noPhoto}</dd>
              <dt className="text-muted">{t.steps.text}</dt>
              <dd className="break-words">{draft.description}</dd>
            </dl>
            <Callout tone="info">{t.anonymous}</Callout>
            <p className="text-xs text-muted">{t.screened}</p>
            {error && <Callout tone="error">{error}</Callout>}
            <button
              className="btn w-full"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  setSent(await submitReport(draft));
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? <Spinner /> : <ShieldAlert className="h-4 w-4" aria-hidden="true" />} {t.send}
            </button>
          </div>
        )}
        {step !== "login" && step !== "category" && (
          <button className="btn-quiet" onClick={() => go(ORDER[Math.max(1, ORDER.indexOf(step) - 1)]!)}>{t.back}</button>
        )}
      </div>
      <p className="text-xs text-muted">{t.emergency}</p>
    </Shell>
  );
}

type Text = ReturnType<typeof useText>;

function Shell({ t, children }: { t: Text; children: React.ReactNode }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl animate-rise-in space-y-4 px-4 py-6">
        <header className="space-y-1">
          <p className="label">{t.kicker}</p>
          <h1 className="text-2xl font-bold leading-tight">{t.title}</h1>
          <p className="text-sm text-muted">{t.lead}</p>
        </header>
        {children}
      </div>
    </div>
  );
}

function LoginStep({ t, onDone }: { t: Text; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      <button
        className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded bg-[#0066CC] px-4 font-semibold text-white hover:bg-[#004d99] sm:w-auto"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const r = await demoSpidSignIn();
          setBusy(false);
          if (r.ok) onDone();
          else setErr(r.reason);
        }}
      >
        {busy ? <Spinner /> : <span aria-hidden="true" className="rounded-sm bg-white px-1 text-xs font-black text-[#0066CC]">ID</span>}
        {t.spid}
      </button>
      <div className="inline-flex items-center rounded-sm border border-estimated/50 bg-estimated/15 px-1.5 py-0.5 text-2xs font-bold uppercase tracking-[0.06em] text-estimated">
        {t.spidDemo}
      </div>
      <p className="text-xs text-muted">{t.spidNote}</p>
      {err && <Callout tone="error" title={t.spidFailed}>{err}</Callout>}
    </div>
  );
}

function GpsStep({ t, draft, onFix }: { t: Text; draft: ReportDraft; onFix: (g: NonNullable<ReportDraft["gps"]>) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      <h2 className="flex items-center gap-2 text-lg font-bold"><MapPin className="h-5 w-5 text-link" aria-hidden="true" />{t.gpsTitle}</h2>
      <p className="text-sm text-muted">{t.gpsLead}</p>
      {draft.gps && <Callout tone="info">{t.gpsOk(String(Math.round(draft.gps.accuracy_m ?? 0)))}</Callout>}
      {draft.gps && !(draft.gps.lat >= 41.4 && draft.gps.lat <= 42.4 && draft.gps.lon >= 12 && draft.gps.lon <= 13.1) && (
        <Callout tone="error">{t.gpsOutside}</Callout>
      )}
      {err && <Callout tone="error">{err}</Callout>}
      <button
        className="btn"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setErr(null);
          try {
            onFix(await getDeviceGps());
          } catch (e) {
            setErr(t.gpsErr[(e as GpsError) in t.gpsErr ? (e as GpsError) : "unavailable"]);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? <Spinner /> : <LocateFixed className="h-4 w-4" aria-hidden="true" />} {t.gpsButton}
      </button>
    </div>
  );
}

function PhotoStep({ t, draft, onPhoto, onSkip }: { t: Text; draft: ReportDraft; onPhoto: (p: Partial<ReportDraft>) => void; onSkip?: () => void }) {
  const [problems, setProblems] = useState<PhotoProblem[]>([]);
  const [busy, setBusy] = useState(false);
  const [camera, setCamera] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const gps = draft.gps!;

  async function fromGallery(file: File) {
    setBusy(true);
    setErr(null);
    try {
      const check = checkPhoto(await photoMetaOf(file), gps);
      setProblems(check.problems);
      if (check.problems.length === 0)
        onPhoto({ photo: await reencodeWithoutMetadata(file), photoSource: "gallery", photoGpsDistanceM: check.distanceM, photoAgeMin: check.ageMin });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function fromCamera(video: HTMLVideoElement) {
    // Taken live in the app: position and time come from the device at the moment of the shot.
    setBusy(true);
    try {
      const fix = await getDeviceGps();
      const photo = await reencodeWithoutMetadata(video);
      const check = checkPhoto({ lat: fix.lat, lon: fix.lon, takenAt: new Date() }, gps);
      setProblems(check.problems);
      setCamera(false);
      if (check.problems.length === 0) onPhoto({ photo, photoSource: "camera", photoGpsDistanceM: check.distanceM, photoAgeMin: check.ageMin });
    } catch {
      setErr(t.gpsErr.unavailable);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-bold">{t.photoTitle}</h2>
      <p className="text-sm text-muted">{t.photoLead}</p>
      {camera ? (
        <LiveCamera t={t} busy={busy} onShot={fromCamera} onCancel={() => setCamera(false)} onError={() => { setCamera(false); setErr(t.cameraErr); }} />
      ) : (
        <div className="flex flex-wrap gap-2">
          <button className="btn" onClick={() => setCamera(true)}><Camera className="h-4 w-4" aria-hidden="true" />{t.shoot}</button>
          <label className="btn-ghost cursor-pointer">
            {busy ? <Spinner /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
            {t.gallery}
            <input type="file" accept="image/jpeg" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void fromGallery(f); e.target.value = ""; }} />
          </label>
        </div>
      )}
      {problems.map((p) => <Callout key={p} tone="error">{t.problems[p]}</Callout>)}
      {err && <Callout tone="error">{err}</Callout>}
      {draft.photo && draft.photoGpsDistanceM !== null && (
        <>
          <PhotoPreview blob={draft.photo} />
          <Callout tone="info">{t.photoOk(draft.photoGpsDistanceM, draft.photoAgeMin ?? 0)}</Callout>
        </>
      )}
      {onSkip && (
        <div className="space-y-1">
          <p className="text-xs text-muted">{t.photoOptional}</p>
          <button className="btn-ghost" onClick={onSkip}>{t.skipPhoto}</button>
        </div>
      )}
      <p className="text-xs text-muted">{t.privacy}</p>
    </div>
  );
}

function LiveCamera({ t, busy, onShot, onCancel, onError }: { t: Text; busy: boolean; onShot: (v: HTMLVideoElement) => void; onCancel: () => void; onError: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    let stream: MediaStream | null = null;
    let stopped = false;
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        if (stopped) return s.getTracks().forEach((tr) => tr.stop());
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play();
        }
      })
      .catch(onError) ?? onError();
    return () => {
      stopped = true;
      stream?.getTracks().forEach((tr) => tr.stop());
    };
  }, [onError]);
  return (
    <div className="space-y-2">
      <video ref={video} playsInline muted className="aspect-[4/3] w-full rounded bg-black object-cover" />
      <div className="flex gap-2">
        <button className="btn" disabled={busy} onClick={() => video.current && onShot(video.current)}>
          {busy ? <Spinner /> : <Camera className="h-4 w-4" aria-hidden="true" />} {t.snap}
        </button>
        <button className="btn-quiet" onClick={onCancel}>{t.cancel}</button>
      </div>
    </div>
  );
}

function PhotoPreview({ blob }: { blob: Blob | null }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return setUrl(null);
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url ? <img src={url} alt="" className="max-h-64 w-full rounded border border-line object-contain" /> : null;
}

