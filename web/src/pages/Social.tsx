// Sociale: where to do a sport, or which museums and galleries to visit, on the day and at the time you choose.
// Each place is a 3D marker on the city (green = open then, grey = closed, blue = hours unknown) and a row in the list.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Clock } from "lucide-react";
import { KindBadge } from "@/components/Badge";
import { Chips, CitizenMap, MapScreen, PositionBar } from "@/components/CitizenMap";
import { GlyphIcon, ResourceDetail } from "@/components/MarkerCard";
import { Callout, Field, Skeleton } from "@/components/ui";
import type { OpenPlace } from "@/lib/here";
import { texts, tr } from "@/lib/i18n";
import type { Resource } from "@/lib/resource";
import { screenPath } from "@/lib/tiers";
import { usePlacesOpen, type Loaded } from "@/lib/useCitizenData";
import { usePosition } from "@/lib/usePosition";
import { useTheme } from "@/lib/useTheme";
import type { MapFocus } from "@/map/CityMap";
import type { Marker } from "@/map/markers";

type Kind = "sport" | "museum";

/** Sports offered as quick choices. Basis: the most common disciplines in the Roma Capitale facility register. */
const SPORTS = ["calcio", "calcetto", "nuoto", "tennis", "padel", "basket", "pallavolo", "atletica", "palestra"];

const T = texts({
  en: {
    choose: "What are you looking for",
    kind: { sport: "Sport", museum: "Museums and galleries" } as Record<Kind, string>,
    when: "Day and time",
    sport: "Which sport",
    anySport: "Any sport",
    near: "Near a point (optional)",
    nearHint: "With a point chosen, only places within about 3 km are listed.",
    open: "Open",
    closed: "Closed",
    unknown: "Hours not known",
    openThen: "Open at that time",
    results: (n: number) => (n === 1 ? "1 place" : `${n} places`),
    coverage: (a: number, b: number) =>
      a === 0 ? "Opening hours are not connected yet: check before you go." : `Opening hours are known for ${a} of ${b} places. For the others, check before you go.`,
    none: "No place found for this choice. Try another time, sport or point.",
    missingSport: "The list of places open at a chosen time is not connected yet.",
    missingMuseum: "The list of museums and galleries is not connected yet.",
    sportMap: "Open the map of sports facilities",
    error: "The places could not be loaded right now.",
    address: "Address",
    hours: "Opening hours",
    type: "Type",
    source: "Source",
    state: "At the time you chose",
  },
  it: {
    choose: "Che cosa cerchi",
    kind: { sport: "Sport", museum: "Musei e gallerie" } as Record<Kind, string>,
    when: "Giorno e ora",
    sport: "Quale sport",
    anySport: "Qualsiasi sport",
    near: "Vicino a un punto (facoltativo)",
    nearHint: "Con un punto scelto, vedi solo i luoghi entro circa 3 km.",
    open: "Aperto",
    closed: "Chiuso",
    unknown: "Orari non noti",
    openThen: "Aperto a quell'ora",
    results: (n: number) => (n === 1 ? "1 luogo" : `${n} luoghi`),
    coverage: (a: number, b: number) =>
      a === 0 ? "Gli orari non sono ancora collegati: controlla prima di andare." : `Gli orari sono noti per ${a} luoghi su ${b}. Per gli altri, controlla prima di andare.`,
    none: "Nessun luogo trovato per questa scelta. Prova un altro orario, sport o punto.",
    missingSport: "L'elenco dei luoghi aperti a un orario scelto non è ancora collegato.",
    missingMuseum: "L'elenco di musei e gallerie non è ancora collegato.",
    sportMap: "Apri la mappa degli impianti sportivi",
    error: "Al momento non è stato possibile caricare i luoghi.",
    address: "Indirizzo",
    hours: "Orari",
    type: "Tipo",
    source: "Fonte",
    state: "All'ora che hai scelto",
  },
});

/** Value for a datetime-local input: the next half hour from now, in local time. */
function nextHalfHour(): string {
  const d = new Date(Date.now() + 30 * 60_000);
  d.setMinutes(d.getMinutes() < 30 ? 0 : 30, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const stateText = (open: boolean | null): string => (open === true ? tr(T).open : open === false ? tr(T).closed : tr(T).unknown);

function placeResource(p: OpenPlace, kind: Kind): Resource {
  const t = tr(T);
  return {
    glyph: kind === "sport" ? "sport" : "museum",
    title: p.name,
    category: p.category ?? t.kind[kind],
    readings: [],
    facts: [
      { label: t.state, value: stateText(p.open) },
      ...(p.address ? [{ label: t.address, value: p.address }] : []),
      ...(p.hours ? [{ label: t.hours, value: p.hours }] : []),
      ...(p.source ? [{ label: t.source, value: p.source }] : []),
    ],
    extra: [],
    synthetic: false,
    position: p.position,
  };
}

function StateChip({ open }: { open: boolean | null }) {
  const cls = open === true ? "border-real/45 bg-real/10 text-real" : open === false ? "border-line-strong bg-sunken text-muted" : "border-estimated/45 bg-estimated/10 text-estimated";
  return <span className={`shrink-0 whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-2xs font-bold uppercase tracking-[0.06em] ${cls}`}>{stateText(open)}</span>;
}

/** No heatmap on this screen: the map only carries the places. */
const NO_HEAT: Loaded<never> = { status: "idle" };

export default function Social() {
  const t = tr(T);
  const { palette } = useTheme();
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get("cosa") === "musei" ? "museum" : "sport";
  const [at, setAt] = useState(nextHalfHour);
  const [sport, setSport] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const { position } = usePosition();
  const atIso = useMemo(() => {
    const d = new Date(at);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }, [at]);
  const query = useMemo(
    () => (atIso ? { kind, at: atIso, ...(kind === "sport" && sport ? { sport } : {}), point: position ? { lon: position.lon, lat: position.lat } : null } : null),
    [kind, atIso, sport, position],
  );
  const res = usePlacesOpen(query);
  // Open places first, then the ones with unknown hours, then the closed ones.
  const places = useMemo(() => {
    const rank = (p: OpenPlace) => (p.open === true ? 0 : p.open === null ? 1 : 2);
    return res.status === "ok" ? [...res.data.places].sort((a, b) => rank(a) - rank(b)) : [];
  }, [res]);

  const markers = useMemo<Marker<number>[]>(
    () =>
      places.map((p, i) => ({
        id: `pl${i}`,
        position: p.position,
        color: p.open === true ? palette.good : p.open === false ? palette.inactive : palette.point,
        level: null,
        glyph: kind === "sport" ? "sport" : "museum",
        data: i,
      })),
    [places, palette, kind],
  );
  const open = selected !== null ? places[selected] : undefined;
  const openPlace = (i: number) => {
    setSelected(i);
    const p = places[i]?.position;
    if (p) setFocus({ lon: p[0], lat: p[1], zoom: 15, pitch: 55 });
  };

  const sheet = (
    <>
      <Chips
        label={t.choose}
        value={kind}
        onChange={(k) => {
          setSelected(null);
          setParams({ cosa: k === "museum" ? "musei" : "sport" }, { replace: true });
        }}
        options={[
          { id: "sport", label: t.kind.sport, glyph: "sport" },
          { id: "museum", label: t.kind.museum, glyph: "museum" },
        ]}
      />
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        <div className="grid grid-cols-2 gap-2">
          <Field label={t.when} className={kind === "sport" ? "" : "col-span-2"}>
            <input type="datetime-local" className="input min-h-11" value={at} onChange={(e) => setAt(e.target.value)} />
          </Field>
          {kind === "sport" && (
            <Field label={t.sport}>
              <select className="input min-h-11" value={sport} onChange={(e) => setSport(e.target.value)}>
                <option value="">{t.anySport}</option>
                {SPORTS.map((s) => (
                  <option key={s} value={s}>
                    {s[0]!.toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </select>
            </Field>
          )}
        </div>
        <section className="space-y-1.5">
          <h2 className="label">{t.near}</h2>
          <PositionBar />
          {position && <p className="hint">{t.nearHint}</p>}
        </section>

        {res.status === "loading" && <Skeleton lines={4} />}
        {res.status === "missing" && (
          <Callout tone="warn">
            {kind === "sport" ? t.missingSport : t.missingMuseum}
            {kind === "sport" && (
              <Link to={screenPath("public", "sport") ?? "/"} className="mt-1 flex items-center gap-1 font-semibold text-link hover:underline">
                {t.sportMap}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            )}
          </Callout>
        )}
        {res.status === "error" && (
          <Callout tone="error" title={t.error}>
            {res.text}
          </Callout>
        )}
        {res.status === "ok" && (
          <>
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-bold text-ink">
                {t.results(places.length)}
                {(res.data.coverage?.withHours ?? 1) > 0 && (
                  <span className="ml-2 inline-flex items-center gap-1 text-xs font-normal text-muted">
                    <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                    {places.filter((p) => p.open === true).length} {t.openThen.toLowerCase()}
                  </span>
                )}
              </h2>
              {res.kind && <KindBadge kind={res.kind} />}
            </div>
            {res.data.coverage && res.data.coverage.withHours < res.data.coverage.total && (
              <p className="hint">{t.coverage(res.data.coverage.withHours, res.data.coverage.total)}</p>
            )}
            {places.length === 0 && <p className="text-sm text-muted">{t.none}</p>}
            <ul className="space-y-1.5">
              {places.slice(0, 80).map((p, i) => (
                <li key={`${p.name}-${i}`}>
                  <button
                    type="button"
                    onClick={() => openPlace(i)}
                    className={`flex w-full items-start gap-2.5 rounded border px-3 py-2 text-left transition-colors duration-150 ${
                      selected === i ? "border-link bg-primary-soft" : "border-line hover:border-line-strong"
                    }`}
                  >
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-simulated/10 text-simulated">
                      <GlyphIcon glyph={kind === "sport" ? "sport" : "museum"} className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold leading-snug text-ink">{p.name}</span>
                      <span className="block truncate text-xs text-muted">{[p.address, p.hours].filter(Boolean).join(" · ")}</span>
                    </span>
                    <StateChip open={p.open} />
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
        heat={NO_HEAT}
        heatLabel=""
        unit=""
        markers={markers}
        selectedId={selected !== null ? `pl${selected}` : null}
        onPickMarker={(m) => (m ? openPlace(m.data) : setSelected(null))}
        describeMarker={(m) => ({ title: places[m.data]?.name ?? "", line: places[m.data] ? stateText(places[m.data]!.open) : undefined })}
        focus={focus}
      >
        {open && <ResourceDetail resource={placeResource(open, kind)} kind={res.status === "ok" ? res.kind : undefined} onClose={() => setSelected(null)} />}
      </CitizenMap>
    </MapScreen>
  );
}
