import { useCallback, useEffect, useMemo, useState } from "react";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Check, ListChecks, Megaphone, RefreshCw, Route, Sparkles, Truck, Wrench, X } from "lucide-react";
import { CityMap, type MapFocus } from "@/map/CityMap";
import { markerLayers, pickedMarker, type Marker } from "@/map/markers";
import type { Glyph } from "@/map/markerGlyphs";
import { ResourceHover } from "@/components/MarkerCard";
import type { Resource } from "@/lib/resource";
import { TWIN_START_ZOOM } from "@/lib/twinOverlay";
import { useTheme } from "@/lib/useTheme";
import { Callout, EmptyState, MapFloat, Panel, Segmented, Skeleton, Spinner, Workspace } from "@/components/ui";
import { KindBadge, SampleBadge } from "@/components/Badge";
import { errorText } from "@/lib/errors";
import { locale, texts, tr } from "@/lib/i18n";
import { levelColour, routePath, toPlanEvents, type CrewRoute, type Level, type MaintenancePlan, type SignalEvent, type StaffReportRow, type TwinEvidence, type Verification } from "@/lib/signals";
import { loadStaffReports, photoUrls, planMaintenance, runSignalEvents, setReportsStatus, verifyEvent, type Checks } from "@/lib/reportApi";

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
    tabs: { events: "Eventi", plan: "Piano squadre" },
    planLead: "Manda le squadre strade e fogne alle buche, ai tombini e ai cantieri segnalati: prima i più urgenti, con meno strada possibile.",
    roads: "Squadre strade",
    sewers: "Squadre fogne",
    runPlan: "Calcola il piano",
    planSample: "Piano di esempio sugli eventi di esempio.",
    planTotal: (n: number, km: string, h: string, eur: string) => `${n} interventi · ${km} km · ${h} ore · ${eur} €`,
    baseline: (km: string, h: string, eur: string) => `Senza piano (una squadra per ogni segnalazione): ${km} km · ${h} ore · ${eur} €`,
    saving: (p: string) => `Risparmio stimato: ${p}% dei costi`,
    crew: (c: string) => c.replace("roads", "Strade").replace("sewers", "Fogne"),
    stop: (n: number, label: string, min: number) => `${n}. ${label} · arrivo dopo ${min} min`,
    unserved: (n: number) => `${n} interventi non entrano nel turno: restano per il prossimo.`,
    skippedNote: (n: number) => `${n} eventi esclusi (fiducia sotto il 45% e non confermati, oppure non sono lavori per le squadre).`,
    planHonesty: "Distanze in linea d'aria per un fattore di percorso, depositi ipotetici, costi orari stimati: un ordine di grandezza, non un preventivo.",
    markFixed: "Segna come risolto",
    hoverReports: (n: number) => `${n} segnalazion${n === 1 ? "e" : "i"}`,
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
    tabs: { events: "Events", plan: "Crew plan" },
    planLead: "Send road and sewer crews to the reported potholes, drains and worksites: most urgent first, with as little driving as possible.",
    roads: "Road crews",
    sewers: "Sewer crews",
    runPlan: "Plan the crews",
    planSample: "Sample plan on the sample events.",
    planTotal: (n: number, km: string, h: string, eur: string) => `${n} jobs · ${km} km · ${h} hours · €${eur}`,
    baseline: (km: string, h: string, eur: string) => `Without a plan (one crew per report): ${km} km · ${h} hours · €${eur}`,
    saving: (p: string) => `Estimated saving: ${p}% of the cost`,
    crew: (c: string) => c.replace("roads", "Roads").replace("sewers", "Sewers"),
    stop: (n: number, label: string, min: number) => `${n}. ${label} · arrives after ${min} min`,
    unserved: (n: number) => `${n} jobs do not fit in the shift: left for the next one.`,
    skippedNote: (n: number) => `${n} events left out (confidence below 45% and not confirmed, or not a crew job).`,
    planHonesty: "Straight-line distances times a detour factor, hypothetical depots, estimated hourly costs: an order of magnitude, not a quote.",
    markFixed: "Mark as fixed",
    hoverReports: (n: number) => `${n} report${n === 1 ? "" : "s"}`,
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
  const [tab, setTab] = useState<"events" | "plan">("events");
  const [crews, setCrews] = useState({ roads: 2, sewers: 1 });
  const [plan, setPlan] = useState<MaintenancePlan | null>(null);
  const [planSample, setPlanSample] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const [hover, setHover] = useState<{ x: number; y: number; e: SignalEvent } | null>(null);
  const [zoom, setZoom] = useState<number>(TWIN_START_ZOOM);
  const { palette } = useTheme();

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
    const showPlan = tab === "plan" && plan !== null;
    const out: Layer[] = [
      // Shared 3D markers: the column follows the probability that the event is true (public events: one height).
      ...markerLayers(
        events.map(
          (e): Marker<SignalEvent> => ({
            id: e.id,
            position: [e.lon, e.lat],
            color: levelColour(e.level),
            level: e.confidence,
            glyph: glyphOf(e),
            data: e,
          }),
        ),
        { id: "sig", zoom, palette, selectedId: selected, hoveredId: hover?.e.id ?? null },
      ),
    ];
    if (showPlan && plan) {
      out.push(
        new PathLayer<CrewRoute>({
          id: "crew-routes",
          data: plan.routes,
          getPath: routePath,
          getColor: (r) => (r.crew_type === "roads" ? [0, 102, 204, 230] : [0, 140, 120, 230]),
          getWidth: 5,
          widthMinPixels: 3,
          capRounded: true,
          jointRounded: true,
        }) as never,
        new ScatterplotLayer({
          id: "crew-depots",
          data: plan.depots,
          getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
          getRadius: 120,
          radiusUnits: "meters",
          radiusMinPixels: 7,
          getFillColor: [23, 50, 77, 255],
          getLineColor: [255, 255, 255, 255],
          stroked: true,
          lineWidthMinPixels: 2,
        }) as never,
        new TextLayer({
          id: "crew-stop-numbers",
          data: plan.routes.flatMap((r) => r.stops.map((st, i) => ({ ...st, n: i + 1 }))),
          getPosition: (st: { lon: number; lat: number }) => [st.lon, st.lat],
          getText: (st: { n: number }) => String(st.n),
          getSize: 15,
          getColor: [255, 255, 255, 255],
          fontWeight: 700,
          outlineWidth: 3,
          outlineColor: [23, 50, 77, 255],
          fontSettings: { sdf: true },
          getPixelOffset: [0, -18],
        }) as never,
      );
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, selected, plan, tab, zoom, palette, hover?.e.id]);

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
          <Segmented
            label={t.title}
            value={tab}
            onChange={setTab}
            options={[
              { id: "events", label: t.tabs.events, icon: ListChecks },
              { id: "plan", label: t.tabs.plan, icon: Route },
            ]}
          />
          {sample && <Callout tone="warn">{t.sample}</Callout>}
          {error && <Callout tone="error">{error}</Callout>}
          {tab === "plan" && (
            <PlanPanel
              crews={crews}
              setCrews={setCrews}
              plan={plan}
              sample={planSample}
              busy={planBusy}
              disabled={!events?.length}
              onRun={async () => {
                if (!events) return;
                setPlanBusy(true);
                setError(null);
                try {
                  const confirmed = new Set(rows.filter((r) => r.status === "confirmed").map((r) => r.id));
                  const out = await planMaintenance(toPlanEvents(events, confirmed), crews);
                  setPlan(out.plan);
                  setPlanSample(out.sample);
                  // Stay at the zoom that shows the 3D city, centred on the planned stops.
                  const pts = out.plan.routes.flatMap((r) => r.stops);
                  const mid = (v: number[], d: number) => (v.length ? (Math.min(...v) + Math.max(...v)) / 2 : d);
                  setFocus({ lon: mid(pts.map((p) => p.lon), 12.4964), lat: mid(pts.map((p) => p.lat), 41.8902), zoom: TWIN_START_ZOOM, pitch: 50 });
                } catch (e) {
                  setError(errorText(e));
                } finally {
                  setPlanBusy(false);
                }
              }}
              eventLabel={(id) => events?.find((e) => e.id === id)?.category_label ?? id}
            />
          )}
          {tab === "events" && events === null && <Skeleton lines={5} />}
          {tab === "events" && events?.length === 0 && <EmptyState icon={Megaphone} title={t.none}>{t.noneText}</EmptyState>}
          <ul className={`space-y-2 ${tab === "events" ? "" : "hidden"}`}>
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
      <CityMap
        layers={layers}
        pitch={45}
        focus={focus}
        onZoomStep={setZoom}
        onHover={(info: PickingInfo) => {
          const m = pickedMarker<SignalEvent>(info, "sig");
          setHover(m ? { x: info.x, y: info.y, e: m.data } : null);
        }}
        onPick={(info: PickingInfo) => {
          const m = pickedMarker<SignalEvent>(info, "sig");
          if (m) {
            setTab("events");
            select(m.data);
          }
        }}
      />
      {hover && <ResourceHover x={hover.x} y={hover.y} resource={eventResource(hover.e)} kind="real" />}
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

function PlanPanel({
  crews,
  setCrews,
  plan,
  sample,
  busy,
  disabled,
  onRun,
  eventLabel,
}: {
  crews: { roads: number; sewers: number };
  setCrews: (c: { roads: number; sewers: number }) => void;
  plan: MaintenancePlan | null;
  sample: boolean;
  busy: boolean;
  disabled: boolean;
  onRun: () => void;
  eventLabel: (id: string) => string;
}) {
  const t = tr(T);
  const n = (v: number, d = 1) => v.toLocaleString(locale(), { maximumFractionDigits: d });
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">{t.planLead}</p>
      <div className="grid grid-cols-2 gap-2">
        {(["roads", "sewers"] as const).map((k) => (
          <label key={k} className="space-y-1 text-xs font-semibold">
            <span className="flex items-center gap-1">{k === "roads" ? <Wrench className="h-3.5 w-3.5" aria-hidden="true" /> : <Truck className="h-3.5 w-3.5" aria-hidden="true" />}{k === "roads" ? t.roads : t.sewers}</span>
            <input
              type="number"
              min={0}
              max={10}
              className="input"
              value={crews[k]}
              onChange={(e) => setCrews({ ...crews, [k]: Math.max(0, Math.min(10, Number(e.target.value) || 0)) })}
            />
          </label>
        ))}
      </div>
      <button className="btn w-full" disabled={busy || disabled} onClick={onRun}>
        {busy ? <Spinner /> : <Route className="h-4 w-4" aria-hidden="true" />} {t.runPlan}
      </button>
      {plan && (
        <div className="space-y-3">
          {sample && <Callout tone="warn">{t.planSample}</Callout>}
          <div className="rounded border border-line bg-sunken p-3 text-sm">
            <div className="font-semibold">{t.planTotal(plan.total.stops, n(plan.total.km), n(plan.total.hours), n(plan.total.cost_eur, 0))}</div>
            <div className="text-xs text-muted">{t.baseline(n(plan.baseline.km), n(plan.baseline.hours), n(plan.baseline.cost_eur, 0))}</div>
            <div className="mt-1 font-bold text-real">{t.saving(n(plan.savings.cost_pct))}</div>
          </div>
          {plan.unserved.length > 0 && <Callout tone="warn">{t.unserved(plan.unserved.length)}</Callout>}
          <ul className="space-y-2">
            {plan.routes.map((r) => (
              <li key={r.crew} className="rounded border border-line p-2 text-xs">
                <div className="flex items-center justify-between gap-2 text-sm font-semibold">
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: r.crew_type === "roads" ? "rgb(0,102,204)" : "rgb(0,140,120)" }} />
                    {t.crew(r.crew)}
                  </span>
                  <span className="num text-muted">{n(r.km)} km · {n(r.hours)} h</span>
                </div>
                <ol className="mt-1 space-y-0.5">
                  {r.stops.map((st, i) => (
                    <li key={st.id}>{t.stop(i + 1, eventLabel(st.id), st.arrive_min)}</li>
                  ))}
                </ol>
              </li>
            ))}
          </ul>
          {plan.skipped.length > 0 && <p className="hint">{t.skippedNote(plan.skipped.length)}</p>}
          <p className="hint">{t.planHonesty}</p>
        </div>
      )}
    </div>
  );
}

function glyphOf(e: SignalEvent): Glyph {
  if (e.category === "traffic") {
    const top = Object.entries(e.subtypes).sort((a, b) => b[1] - a[1])[0]?.[0];
    return top === "bus" || top === "metro" ? "bus" : top === "congestion" ? "traffic" : "incident";
  }
  return ({ flood: "flood", pothole: "pothole", roadworks: "roadworks", public_event: "event" } as Record<string, Glyph>)[e.category] ?? "report";
}

/** What the shared hover card says about one event. Only counts and the first resident's words; never who reported. */
function eventResource(e: SignalEvent): Resource {
  const t = tr(T);
  return {
    glyph: glyphOf(e),
    title: e.category_label,
    category: t.level[e.level],
    ...(e.confidence !== null ? { main: { label: t.legend, value: pct(e.confidence), unit: "" } } : {}),
    readings: [],
    facts: [
      { label: t.tabs.events, value: t.reports(e.n_reports, e.n_reporters) },
      ...(e.texts[0] ? [{ label: t.texts, value: `«${e.texts[0]}»` }] : []),
    ],
    extra: [],
    observedAt: e.last_seen,
    synthetic: false,
    position: [e.lon, e.lat],
    id: e.id,
  };
}
