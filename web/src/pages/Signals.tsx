import { useCallback, useEffect, useMemo, useState } from "react";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { Check, Megaphone, RefreshCw, Sparkles, X } from "lucide-react";
import { CityMap, type MapFocus } from "@/map/CityMap";
import { Callout, EmptyState, MapFloat, Panel, Skeleton, Spinner, Workspace } from "@/components/ui";
import { KindBadge, SampleBadge } from "@/components/Badge";
import { errorText } from "@/lib/errors";
import { locale, texts, tr } from "@/lib/i18n";
import { levelColour, type Level, type SignalEvent, type StaffReportRow, type TwinEvidence, type Verification } from "@/lib/signals";
import { loadStaffReports, photoUrls, runSignalEvents, setReportsStatus, verifyEvent, type Checks } from "@/lib/reportApi";

const T = texts({
  it: {
    title: "Segnalazioni",
    subtitle: "Segnalazioni dei cittadini unite per luogo, ora e tipo in possibili eventi in corso. Ultime 48 ore.",
    refresh: "Aggiorna",
    none: "Nessuna segnalazione nelle ultime 48 ore",
    noneText: "Quando i cittadini inviano una segnalazione con foto e GPS, compare qui come evento.",
    sample: "Dati di esempio: segnalazioni inventate per la dimostrazione, eventi calcolati dal vero strumento.",
    level: { likely: "Probabile evento", probable: "Possibile evento", unconfirmed: "Da verificare", not_scored: "Evento pubblico segnalato" } as Record<Level, string>,
    reports: (n: number, r: number) => `${n} segnalazion${n === 1 ? "e" : "i"} da ${r} person${r === 1 ? "a" : "e"}`,
    since: (t: string) => `dalle ${t}`,
    stale: "nessuna segnalazione recente",
    gpsMatch: (m: number, x: number) => `Foto con GPS coerente: ${m}${x ? ` · incoerente: ${x}` : ""}`,
    why: "Perché questo grado di fiducia",
    twin: "Cosa dice il gemello digitale",
    verdict: { supports: "conferma", contradicts: "smentisce", neutral: "neutro", not_available: "non disponibile" } as Record<TwinEvidence["verdict"], string>,
    simulated: "include sensori simulati: peso ridotto",
    texts: "Cosa scrivono i cittadini",
    photos: "Foto (senza metadati)",
    verify: "Verifica con Claude + Exa",
    verifyNote: "Una chiamata a Claude (foto e testi) e una ricerca Exa (notizie) per questo evento.",
    photoVerdict: { consistent: "Le foto mostrano l'evento", inconsistent: "Le foto non mostrano l'evento", unclear: "Foto non chiare", no_photo: "Nessuna foto da controllare" } as Record<Verification["photo"], string>,
    newsVerdict: { confirms: "Le notizie confermano", no_match: "Nessuna notizia trovata" } as Record<Verification["news"], string>,
    confirm: "Conferma evento",
    dismiss: "Scarta",
    marked: (s: string) => (s === "confirmed" ? "Segnato come confermato." : "Segnalazioni scartate."),
    factor: (f: string) =>
      ({ prior: "Partenza (evento raro)", reporters: "Persone diverse che segnalano", photos: "Foto allegate", photo_check: "Controllo foto (Claude)", news_check: "Notizie (Exa)" })[f] ??
      (f.startsWith("twin:") ? `Gemello digitale: ${f.slice(5)}` : f),
    honesty: "Le segnalazioni non sono verificate finché un operatore non le conferma. La fiducia è un modello, non un fatto.",
    noIdentity: "Chi ha segnalato non è visibile: ogni account conta una volta sola.",
    legend: "Fiducia",
  },
  en: {
    title: "Reports",
    subtitle: "Citizen reports merged by place, time and type into possible live events. Last 48 hours.",
    refresh: "Refresh",
    none: "No reports in the last 48 hours",
    noneText: "When residents send a report with a photo and GPS it shows up here as an event.",
    sample: "Sample data: reports made up for the demo, events computed by the real tool.",
    level: { likely: "Likely event", probable: "Possible event", unconfirmed: "To be checked", not_scored: "Reported public event" },
    reports: (n: number, r: number) => `${n} report${n === 1 ? "" : "s"} from ${r} ${r === 1 ? "person" : "people"}`,
    since: (t: string) => `since ${t}`,
    stale: "no recent report",
    gpsMatch: (m: number, x: number) => `Photo GPS matching: ${m}${x ? ` · not matching: ${x}` : ""}`,
    why: "Why this confidence",
    twin: "What the digital twin says",
    verdict: { supports: "agrees", contradicts: "disagrees", neutral: "neutral", not_available: "not available" },
    simulated: "includes simulated sensors: reduced weight",
    texts: "What residents wrote",
    photos: "Photos (metadata removed)",
    verify: "Check with Claude + Exa",
    verifyNote: "One Claude call (photos and texts) and one Exa search (news) for this event.",
    photoVerdict: { consistent: "Photos show the event", inconsistent: "Photos do not show the event", unclear: "Photos unclear", no_photo: "No photo to check" },
    newsVerdict: { confirms: "News confirms it", no_match: "No news found" },
    confirm: "Confirm event",
    dismiss: "Dismiss",
    marked: (s: string) => (s === "confirmed" ? "Marked as confirmed." : "Reports dismissed."),
    factor: (f: string) =>
      ({ prior: "Starting point (events are rare)", reporters: "Different people reporting", photos: "Photos attached", photo_check: "Photo check (Claude)", news_check: "News (Exa)" })[f] ??
      (f.startsWith("twin:") ? `Digital twin: ${f.slice(5)}` : f),
    honesty: "Reports are unverified until an officer confirms them. Confidence is a model, not a fact.",
    noIdentity: "Who reported is not visible: each account counts once.",
    legend: "Confidence",
  },
});

const pct = (p: number | null) => (p === null ? "–" : `${Math.round(p * 100)}%`);

/** Staff layer: citizen reports merged into candidate live events, on the 3D city. */
export default function Signals() {
  const t = tr(T);
  const [rows, setRows] = useState<StaffReportRow[]>([]);
  const [events, setEvents] = useState<SignalEvent[] | null>(null);
  const [sample, setSample] = useState(false);
  const [checks, setChecks] = useState<Checks>({});
  const [verifications, setVerifications] = useState<Record<string, Verification>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);

  const refresh = useCallback(async (nextChecks: Checks) => {
    setBusy(true);
    setError(null);
    try {
      const r = await loadStaffReports();
      setRows(r);
      const out = await runSignalEvents(r, nextChecks);
      setEvents(out.result.events);
      setSample(out.sample);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh({});
  }, [refresh]);

  const event = events?.find((e) => e.id === selected) ?? null;

  const layers = useMemo(() => {
    if (!events) return [];
    return [
      new ScatterplotLayer<SignalEvent>({
        id: "signals",
        data: events,
        getPosition: (e) => [e.lon, e.lat],
        getRadius: (e) => Math.max(e.radius_m, 90),
        radiusUnits: "meters",
        radiusMinPixels: 9,
        getFillColor: (e) => [...levelColour(e.level), e.stale ? 70 : 150] as [number, number, number, number],
        getLineColor: (e) => (e.id === selected ? [0, 0, 0, 255] : [255, 255, 255, 230]),
        lineWidthMinPixels: 2,
        stroked: true,
        pickable: true,
        onClick: (info) => info.object && setSelected(info.object.id),
        updateTriggers: { getLineColor: selected },
      }),
      new TextLayer<SignalEvent>({
        id: "signals-count",
        data: events,
        getPosition: (e) => [e.lon, e.lat],
        getText: (e) => String(e.n_reports),
        getSize: 14,
        getColor: [255, 255, 255, 255],
        fontWeight: 700,
        outlineWidth: 2,
        outlineColor: [0, 0, 0, 160],
        fontSettings: { sdf: true },
      }),
    ];
  }, [events, selected]);

  const select = (e: SignalEvent) => {
    setSelected(e.id);
    setFocus({ lon: e.lon, lat: e.lat, zoom: 15.5, pitch: 45 });
  };

  return (
    <Workspace
      panel={
        <Panel
          title={t.title}
          subtitle={t.subtitle}
          icon={Megaphone}
          width="w-[25rem]"
          actions={
            <button className="btn-quiet" onClick={() => void refresh(checks)} disabled={busy} title={t.refresh} aria-label={t.refresh}>
              {busy ? <Spinner /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            </button>
          }
          footer={<p className="hint">{t.honesty} {t.noIdentity}</p>}
        >
          {sample && <Callout tone="warn">{t.sample}</Callout>}
          {error && <Callout tone="error">{error}</Callout>}
          {events === null && <Skeleton lines={5} />}
          {events?.length === 0 && <EmptyState icon={Megaphone} title={t.none}>{t.noneText}</EmptyState>}
          <ul className="space-y-2">
            {events?.map((e) => (
              <li key={e.id}>
                <EventCard
                  e={e}
                  open={e.id === selected}
                  onSelect={() => select(e)}
                  verification={verifications[e.id]}
                  live={!sample}
                  onVerified={(v) => {
                    setVerifications((all) => ({ ...all, [e.id]: v }));
                    const next = { ...checks, [e.id]: { photo: v.photo, news: v.news } };
                    setChecks(next);
                    void refresh(next);
                  }}
                  onStatus={async (status) => {
                    await setReportsStatus(e.report_ids, status);
                    void refresh(checks);
                  }}
                  rows={rows}
                />
              </li>
            ))}
          </ul>
        </Panel>
      }
    >
      <CityMap layers={layers} pitch={35} focus={focus} />
      <MapFloat position="bottom-left">
        <div className="space-y-1 text-xs">
          <div className="font-semibold">{t.legend}</div>
          {(["likely", "probable", "unconfirmed", "not_scored"] as Level[]).map((l) => (
            <div key={l} className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: `rgb(${levelColour(l).join(",")})` }} />
              {t.level[l]}
            </div>
          ))}
          {sample && <SampleBadge />}
        </div>
      </MapFloat>
      {event && (
        <MapFloat position="top-left">
          <div className="text-sm font-semibold">{event.category_label}</div>
          <div className="text-xs text-muted">{t.level[event.level]} · {pct(event.confidence)}</div>
        </MapFloat>
      )}
    </Workspace>
  );
}

function EventCard({
  e,
  open,
  onSelect,
  verification,
  live,
  onVerified,
  onStatus,
  rows,
}: {
  e: SignalEvent;
  open: boolean;
  onSelect: () => void;
  verification?: Verification;
  live: boolean;
  onVerified: (v: Verification) => void;
  onStatus: (s: "confirmed" | "dismissed") => Promise<void>;
  rows: StaffReportRow[];
}) {
  const t = tr(T);
  const [urls, setUrls] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const time = new Date(e.first_seen).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
  const [r, g, b] = levelColour(e.level);
  const confirmed = rows.some((row) => e.report_ids.includes(row.id) && row.status === "confirmed");

  useEffect(() => {
    if (open && live && urls.length === 0 && e.photo_refs.length) void photoUrls(e.photo_refs.slice(0, 6)).then(setUrls);
  }, [open, live, e.photo_refs, urls.length]);

  return (
    <div className={`rounded border bg-surface transition-colors ${open ? "border-link" : "border-line hover:border-line-strong"}`}>
      <button className="flex w-full items-start gap-3 p-3 text-left" onClick={onSelect} aria-expanded={open}>
        <span className="mt-1 inline-block h-3 w-3 shrink-0 rounded-full" style={{ background: `rgb(${r},${g},${b})` }} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span className="font-semibold">{e.category_label}</span>
            <span className="num text-sm font-bold">{pct(e.confidence)}</span>
          </span>
          <span className="block text-xs text-muted">
            {t.level[e.level]} · {t.reports(e.n_reports, e.n_reporters)} · {t.since(time)}
            {e.stale ? ` · ${t.stale}` : ""}
            {confirmed ? " · ✓" : ""}
          </span>
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line p-3 text-sm">
          {e.confidence !== null && (
            <div className="h-2 overflow-hidden rounded bg-sunken" role="meter" aria-valuenow={Math.round(e.confidence * 100)} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full" style={{ width: pct(e.confidence), background: `rgb(${r},${g},${b})` }} />
            </div>
          )}
          <p className="text-xs text-muted">{t.gpsMatch(e.n_location_match, e.n_location_mismatch)}</p>

          <div>
            <div className="label mb-1">{t.why}</div>
            <ul className="space-y-0.5 text-xs">
              {e.factors.map((f) => (
                <li key={f.factor} className="flex justify-between gap-2">
                  <span>{t.factor(f.factor)}</span>
                  <span className="num text-muted">{f.lr === null ? pct(f.p ?? 0) : `×${f.lr.toLocaleString(locale(), { maximumFractionDigits: 2 })}`}</span>
                </li>
              ))}
            </ul>
          </div>

          {e.twin.length > 0 && (
            <div>
              <div className="label mb-1">{t.twin}</div>
              <ul className="space-y-1 text-xs">
                {e.twin.map((w) => (
                  <li key={w.layer} className="flex flex-wrap items-center gap-1.5">
                    <span className="font-semibold">{w.layer}</span>
                    {w.value !== null && <span className="num">{w.value.toLocaleString(locale())} {w.unit ?? ""}</span>}
                    <span className={w.verdict === "supports" ? "text-real" : w.verdict === "contradicts" ? "text-danger" : "text-muted"}>{t.verdict[w.verdict]}</span>
                    {w.simulated_input && <KindBadge kind="simulated" text={t.simulated} />}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {e.texts.length > 0 && (
            <div>
              <div className="label mb-1">{t.texts}</div>
              <ul className="space-y-1">
                {e.texts.slice(0, 6).map((x, i) => (
                  <li key={i} className="rounded bg-sunken px-2 py-1 text-xs">«{x}»</li>
                ))}
              </ul>
            </div>
          )}

          {urls.length > 0 && (
            <div>
              <div className="label mb-1">{t.photos}</div>
              <div className="grid grid-cols-3 gap-1.5">
                {urls.map((u) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer">
                    <img src={u} alt="" className="aspect-square w-full rounded object-cover" />
                  </a>
                ))}
              </div>
            </div>
          )}

          {verification && (
            <Callout tone={verification.photo === "inconsistent" ? "warn" : "info"} title={`${t.photoVerdict[verification.photo]} · ${t.newsVerdict[verification.news]}`}>
              {verification.reason}
              {verification.news_results.slice(0, 3).map((n) => (
                <a key={n.url} href={n.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-link underline">{n.title || n.url}</a>
              ))}
            </Callout>
          )}
          {err && <Callout tone="error">{err}</Callout>}
          {done && <Callout tone="info">{done}</Callout>}

          {live && (
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-sm"
                disabled={busy}
                title={t.verifyNote}
                onClick={async () => {
                  setBusy(true);
                  setErr(null);
                  try {
                    onVerified(await verifyEvent(e, null, urls.length ? urls : await photoUrls(e.photo_refs.slice(0, 3))));
                  } catch (x) {
                    setErr(errorText(x));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? <Spinner /> : <Sparkles className="h-4 w-4" aria-hidden="true" />} {t.verify}
              </button>
              <button className="btn-ghost btn-sm" onClick={() => void onStatus("confirmed").then(() => setDone(t.marked("confirmed")), (x) => setErr(errorText(x)))}>
                <Check className="h-4 w-4" aria-hidden="true" /> {t.confirm}
              </button>
              <button className="btn-quiet btn-sm" onClick={() => void onStatus("dismissed").then(() => setDone(t.marked("dismissed")), (x) => setErr(errorText(x)))}>
                <X className="h-4 w-4" aria-hidden="true" /> {t.dismiss}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
