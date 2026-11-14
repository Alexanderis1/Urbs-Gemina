// Trasporti: where the roads are slow now and in the next hours, and what is changing roads and public
// transport today (roadworks, closures, strikes). Events are 3D markers on the city; the list is in the sheet.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { KindBadge } from "@/components/Badge";
import { LiveBadge } from "@/components/LiveBadge";
import { rampColor, trafficColor } from "@/lib/colors";
import { Chips, CitizenMap, HeatLegend, LevelPill, MapScreen, PositionBar } from "@/components/CitizenMap";
import { GlyphIcon, ResourceDetail } from "@/components/MarkerCard";
import { Callout, Skeleton } from "@/components/ui";
import type { TransportEvent } from "@/lib/here";
import { locale, texts, tr } from "@/lib/i18n";
import { formatValue, metricInfo } from "@/lib/layers";
import type { Resource } from "@/lib/resource";
import { useHeatmap, useTransportNow } from "@/lib/useCitizenData";
import { usePosition } from "@/lib/usePosition";
import { useTheme } from "@/lib/useTheme";
import type { MapFocus } from "@/map/CityMap";
import type { Glyph } from "@/map/markerGlyphs";
import type { Marker } from "@/map/markers";

type LensId = "now" | "h1" | "h3" | "bus";
/** Hours ahead for each traffic view (0 = now). Basis: the predicted-congestion input of city_heatmap. */
const AHEAD: Record<LensId, number> = { now: 0, h1: 1, h3: 3, bus: 0 };

const CATEGORY_GLYPH: Record<string, Glyph> = {
  lavori: "roadworks",
  chiusura: "strike",
  deviazione: "bus",
  sciopero: "strike",
  evento: "event",
  avviso: "info",
  segnalazione: "report",
  protezione_civile: "info",
};

const T = texts({
  en: {
    title: "Transport",
    choose: "Map shown",
    lens: { now: "Traffic now", h1: "In 1 hour", h3: "In 3 hours", bus: "Bus delays" } as Record<LensId, string>,
    tabs: { traffic: "Traffic", events: "Events" },
    tabsLabel: "Section",
    whatTraffic: "Average speed on the roads of each part of the city. Slower means more congestion.",
    whatForecast: "A forecast from the twin's traffic model, not a measurement.",
    whatBus: "How late buses and trams are running, from the live feed of the transport company.",
    hereSpeed: "Around your point",
    greyRoads: "Grey: no traffic reading nearby",
    onRoads: "Drawn along the main roads. The colour is the average of the area the road crosses, not a reading on that road.",
    cityNow: "The whole city",
    events: "Roadworks, closures, strikes and events",
    noEvents: "No events reported right now.",
    eventsMissing: "The list of roadworks, closures and strikes is not connected yet. The traffic map above is live.",
    eventsError: "The events could not be loaded right now.",
    stale: (id: string, when: string) => `The ${id} feed has not updated since ${when}.`,
    category: {
      lavori: "Roadworks",
      chiusura: "Road closed",
      deviazione: "Line diverted",
      sciopero: "Strike",
      evento: "Event",
      avviso: "Notice",
      segnalazione: "Notice",
      protezione_civile: "Civil protection",
    } as Record<string, string>,
    lines: "Lines",
    street: "Street",
    details: "What it says",
    from: "From",
    until: "Until",
    source: "Source",
    noPosition: "No position on the map",
    count: (n: number) => `${n} on the map`,
  },
  it: {
    title: "Trasporti",
    choose: "Mappa mostrata",
    lens: { now: "Traffico adesso", h1: "Tra 1 ora", h3: "Tra 3 ore", bus: "Ritardi dei bus" } as Record<LensId, string>,
    tabs: { traffic: "Traffico", events: "Eventi" },
    tabsLabel: "Sezione",
    whatTraffic: "Velocità media sulle strade di ogni parte della città. Più lento vuol dire più traffico.",
    whatForecast: "Una previsione del modello di traffico, non una misura.",
    whatBus: "Quanto sono in ritardo autobus e tram, dai dati in tempo reale dell'azienda di trasporto.",
    hereSpeed: "Intorno al tuo punto",
    greyRoads: "Grigio: nessuna rilevazione del traffico vicino",
    onRoads: "Disegnato lungo le strade principali. Il colore è la media della zona attraversata, non una misura su quella strada.",
    cityNow: "Tutta la città",
    events: "Lavori, chiusure, scioperi ed eventi",
    noEvents: "Nessun evento segnalato in questo momento.",
    eventsMissing: "L'elenco di cantieri, chiusure e scioperi non è ancora collegato. La mappa del traffico qui sopra è in tempo reale.",
    eventsError: "Al momento non è stato possibile caricare gli eventi.",
    stale: (id: string, when: string) => `I dati ${id} non si aggiornano dalle ${when}.`,
    category: {
      lavori: "Lavori",
      chiusura: "Strada chiusa",
      deviazione: "Deviazione linea",
      sciopero: "Sciopero",
      evento: "Evento",
      avviso: "Avviso",
      segnalazione: "Avviso",
      protezione_civile: "Protezione civile",
    } as Record<string, string>,
    lines: "Linee",
    street: "Strada",
    details: "Che cosa dice",
    from: "Dal",
    until: "Fino al",
    source: "Fonte",
    noPosition: "Senza posizione sulla mappa",
    count: (n: number) => `${n} sulla mappa`,
  },
});

const when = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

/** The hour the forecast is for: a whole hour, so repeated views ask the same question (and reuse the answer). */
function hourAhead(hours: number): string | null {
  if (!hours) return null;
  const d = new Date(Date.now() + hours * 3600_000);
  d.setMinutes(0, 0, 0);
  return d.toISOString();
}

/** The category in words: ours in the chosen language, otherwise the tool's own. */
const categoryText = (e: TransportEvent): string => tr(T).category[e.category] ?? e.categoryLabel ?? e.category;

function eventResource(e: TransportEvent): Resource {
  const t = tr(T);
  const facts = [
    ...(e.street ? [{ label: t.street, value: e.street }] : []),
    ...(e.description && e.description !== e.title ? [{ label: t.details, value: e.description }] : []),
    ...(e.lines.length ? [{ label: t.lines, value: e.lines.join(", ") }] : []),
    ...(e.start ? [{ label: t.from, value: when(e.start) }] : []),
    ...(e.end ? [{ label: t.until, value: when(e.end) }] : []),
    ...(e.source ? [{ label: t.source, value: e.source }] : []),
  ];
  return {
    glyph: CATEGORY_GLYPH[e.category] ?? "info",
    title: e.title,
    category: categoryText(e),
    readings: [],
    facts,
    extra: [],
    synthetic: false,
    position: e.position,
  };
}

export default function Transport() {
  const t = tr(T);
  const { palette } = useTheme();
  const [params, setParams] = useSearchParams();
  const tab = params.get("vista") === "eventi" ? "events" : "traffic";
  const [lensId, setLensId] = useState<LensId>("now");
  const [selected, setSelected] = useState<number | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const layer = lensId === "bus" ? "transit_delay" : "road_speed";
  const time = useMemo(() => hourAhead(AHEAD[lensId]), [lensId]);
  const heat = useHeatmap(layer, time);
  const now = useTransportNow();
  const { position } = usePosition();
  const events = now.status === "ok" ? now.data.events : [];
  useEffect(() => setSelected(null), [now.status]);

  // Notices stand on the map in their own section; the traffic section leaves the roads clear to read.
  const markers = useMemo<Marker<number>[]>(
    () =>
      (tab === "events" ? events : []).flatMap((e, i) =>
        e.position
          ? [{ id: `ev${i}`, position: e.position, color: e.category === "sciopero" || e.category === "chiusura" ? palette.bad : palette.accent, level: null, glyph: CATEGORY_GLYPH[e.category] ?? "info", data: i }]
          : [],
      ),
    [events, palette, tab],
  );

  // Road speed is in km/h (config/beliefs.yaml road_speed); the tool's traffic bands carry no unit for the value itself.
  const unit = (heat.status === "ok" && heat.data.unit) || (layer === "road_speed" ? "km/h" : "");
  const bands = heat.status === "ok" ? heat.data.legend : [];
  // Traffic in the colours people know from navigation maps; bus delays keep the scale of every other map.
  const ramp = lensId === "bus" ? rampColor : trafficColor;
  const label = lensId === "bus" ? metricInfo("transit_delay").label : metricInfo("road_speed").label;
  // The patch of the city heatmap the chosen point falls in (no extra request).
  const near = useMemo(() => {
    if (heat.status !== "ok" || !position) return null;
    let best = null;
    let bestD = Infinity;
    for (const c of heat.data.cells) {
      const d = (c.lon - position.lon) ** 2 * 0.55 + (c.lat - position.lat) ** 2;
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    return best;
  }, [heat, position]);
  const nearBand = near?.level !== undefined ? bands.find((b) => b.index === near.level) : undefined;
  const open = selected !== null ? events[selected] : undefined;

  const openEvent = (i: number) => {
    setSelected(i);
    const p = events[i]?.position;
    if (p) setFocus({ lon: p[0], lat: p[1], zoom: 14.5, pitch: 50 });
  };

  const sheet = (
    <>
      <Chips
        label={t.tabsLabel}
        value={tab}
        onChange={(id) => setParams({ vista: id === "events" ? "eventi" : "traffico" }, { replace: true })}
        options={[
          { id: "traffic", label: t.tabs.traffic, glyph: "traffic" },
          { id: "events", label: now.status === "ok" ? `${t.tabs.events} (${events.length})` : t.tabs.events, glyph: "roadworks" },
        ]}
      />
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {tab === "traffic" ? (
          <>
            <div className="-mx-3 -mt-3">
              <Chips
                label={t.choose}
                value={lensId}
                onChange={setLensId}
                options={(Object.keys(AHEAD) as LensId[]).map((id) => ({ id, label: t.lens[id] }))}
              />
            </div>
            <p className="text-sm text-muted">
              {lensId === "bus" ? t.whatBus : t.whatTraffic} {AHEAD[lensId] > 0 && <span className="font-semibold text-ink">{t.whatForecast}</span>}
            </p>
            <PositionBar />
            {near && (
              <div className="rounded border border-line bg-sunken px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-muted">
                    {label} · {t.hereSpeed}
                  </span>
                  {heat.status === "ok" && heat.kind && <KindBadge kind={heat.kind} />}
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="num text-4xl font-bold leading-none text-ink">{formatValue(near.value)}</span>
                  <span className="text-sm text-muted">{unit}</span>
                  {nearBand && <LevelPill index={nearBand.index} label={nearBand.label} bands={bands} ramp={ramp} />}
                </div>
              </div>
            )}
            {heat.status === "loading" && <Skeleton lines={2} />}
            {heat.status === "ok" && (
              <section className="space-y-1.5 rounded border border-line px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="label">
                    {t.cityNow} · {t.lens[lensId]}
                  </h2>
                  {heat.kind && <KindBadge kind={heat.kind} />}
                </div>
                <HeatLegend heat={heat.data} unit={unit} invert={lensId !== "bus"} ramp={ramp} />
                <p className="hint">{t.onRoads}</p>
                {lensId !== "bus" && (
                  <p className="flex items-center gap-2 text-xs text-muted">
                    <span className="inline-block h-1.5 w-6 shrink-0 rounded-full" style={{ background: "rgb(176 184 194)" }} aria-hidden="true" />
                    {t.greyRoads}
                  </p>
                )}
                {heat.live && <LiveBadge live={heat.live} />}
              </section>
            )}
          </>
        ) : (
          <>
            <h1 className="text-base font-bold leading-tight">{t.events}</h1>
            {now.status === "loading" && <Skeleton lines={4} />}
            {now.status === "missing" && <Callout tone="warn">{t.eventsMissing}</Callout>}
            {now.status === "error" && (
              <Callout tone="error" title={t.eventsError}>
                {now.text}
              </Callout>
            )}
            {now.status === "ok" &&
              now.data.feeds
                .filter((f) => f.stale)
                .map((f) => (
                  <Callout key={f.id} tone="warn">
                    {t.stale(f.id, f.lastUpdate ? when(f.lastUpdate) : "?")}
                  </Callout>
                ))}
            {now.status === "ok" && events.length === 0 && <p className="text-sm text-muted">{t.noEvents}</p>}
            <ul className="space-y-1.5">
              {events.map((e, i) => (
                <li key={`${e.title}-${i}`}>
                  <button
                    type="button"
                    onClick={() => openEvent(i)}
                    className={`flex w-full items-start gap-2.5 rounded border px-3 py-2 text-left transition-colors duration-150 ${
                      selected === i ? "border-link bg-primary-soft" : "border-line hover:border-line-strong"
                    }`}
                  >
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-link">
                      <GlyphIcon glyph={CATEGORY_GLYPH[e.category] ?? "info"} className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold leading-snug text-ink">{e.title}</span>
                      <span className="block text-xs text-muted">
                        {categoryText(e)}
                        {e.street && ` · ${e.street}`}
                        {e.lines.length > 0 && ` · ${t.lines} ${e.lines.slice(0, 6).join(", ")}`}
                        {!e.position && ` · ${t.noPosition}`}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </>
  );

  return (
    <MapScreen sheet={sheet}>
      <CitizenMap<number>
        heat={heat}
        heatLabel={label}
        unit={unit}
        invert={lensId !== "bus"}
        onRoads
        greyUnsure={lensId !== "bus"}
        ramp={ramp}
        markers={markers}
        selectedId={selected !== null ? `ev${selected}` : null}
        onPickMarker={(m) => (m ? openEvent(m.data) : setSelected(null))}
        describeMarker={(m) => ({ title: events[m.data]?.title ?? "", line: events[m.data] ? categoryText(events[m.data]!) : undefined })}
        focus={focus}
      >
        {open && (
          <ResourceDetail resource={eventResource(open)} kind={now.status === "ok" ? now.kind : undefined} onClose={() => setSelected(null)}>
            {open.description && <p className="text-sm leading-relaxed text-ink">{open.description}</p>}
          </ResourceDetail>
        )}
      </CitizenMap>
    </MapScreen>
  );
}
