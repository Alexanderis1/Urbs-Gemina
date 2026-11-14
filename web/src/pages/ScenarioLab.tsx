import { Fragment, useMemo, useState, type ReactNode } from "react";
import { GeoJsonLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  Biohazard,
  CloudRain,
  Crosshair,
  FlaskConical,
  MapPin,
  Play,
  RadioTower,
  Siren,
  ThermometerSun,
  TrafficCone,
  Users,
  Waves,
  X,
  type LucideIcon,
} from "lucide-react";
import { CityMap, type MapFocus } from "@/map/CityMap";
import { markerLayers, pickedMarker, type Marker } from "@/map/markers";
import type { Glyph } from "@/map/markerGlyphs";
import { ResourceDetail, ResourceHover } from "@/components/MarkerCard";
import type { Resource } from "@/lib/resource";
import { TWIN_START_ZOOM } from "@/lib/twinOverlay";
import { boundsOf } from "@/lib/geo";
import { AreaPicker } from "@/components/AreaPicker";
import { KindBadge } from "@/components/Badge";
import { RangeBar } from "@/components/RangeBar";
import { RunMeta } from "@/components/RunMeta";
import { Callout, Field, MapFloat, Panel, Section, Segmented, Skeleton, Spinner, Stat, Workspace } from "@/components/ui";
import { areaLabel, areaToArg, type Area } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import { useTheme } from "@/lib/useTheme";
import type { Envelope, ScenarioResult } from "@/api/types";
import {
  buildScenarioChange,
  changeProblem,
  groupLabel,
  isHeavy,
  needsSmallArea,
  resolveKind,
  scenarioSpec,
  SCENARIO_BANDS,
  SCENARIO_GAUGES,
  SCENARIO_GROUPS,
  SCENARIO_SERVICES,
  SCENARIO_SUBSTANCES,
  SCENARIOS,
  type ScenarioTile,
} from "@/lib/scenario";
import { fmtNumber, keyFigures, MAX_ROWS, rangeText, summariseScenario, unitFor, type PlaceItem, type Quantile } from "@/lib/scenarioResult";
import { errorText } from "@/lib/errors";
import { texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    clickMove: (what: string) => `Click the map to move the ${what}`,
    clickPlace: (what: string) => `Click the map to place the ${what}`,
    longitude: "Longitude",
    latitude: "Latitude",
    howRiver: "How to set the river",
    returnPeriod: "Historic-size flood",
    floodSize: "Flood size",
    yearFlood: (y: string) =>
      y === "200" ? "200-year flood (official medium hazard)" : y === "500" ? "500-year flood (official rare-flood map)" : `${y}-year flood`,
    returnPeriodHint:
      "Scenario, not a forecast: the Tiber flood expected on average once in that many years (official discharge at Ripetta). The 1937 flood was about a 50-year flood.",
    rise: "Rise",
    gaugeLevel: "Gauge level",
    forecast: "Forecast",
    riverGauge: "River gauge",
    waterLevel: "Water level at the gauge",
    riverForecastHint: "Uses the highest level in the river forecast for the coming days.",
    riverRise: "River rise above normal",
    rainSource: "Where the rain comes from",
    amount: "Amount",
    radarNow: "Radar now",
    rain: "Rain",
    over: "Over",
    hours: "hours",
    radarHint: "Uses the rain the radar sees now.",
    rainForecastHint: "Uses the rain forecast.",
    highRiver: "High river, optional",
    eg3: "e.g. 3",
    highRiverHint: "A high Tiber blocks sewer outfalls. Leave empty to ignore.",
    temperatures: "Temperatures",
    enterValues: "Enter values",
    dayMax: "Day maximum",
    nightMin: "Night minimum",
    tempForecastHint: "Uses the temperature forecast for the area.",
    changesToTest: "Changes to test, optional",
    treeCover: "Tree cover added",
    sealed: "Sealed ground removed",
    eg10: "e.g. 10",
    releaseWhere: "Where the release happens",
    pointOnMap: "Point on map",
    namedSite: "Named site",
    hazardousSite: "Hazardous site",
    siteHint: "Name of a listed hazardous (Seveso) site.",
    releasePoint: "release point",
    substance: "Substance",
    releaseRate: "Release rate",
    wind: "Wind",
    windForecast: "Wind forecast",
    enterWind: "Enter wind",
    windSpeed: "Wind speed",
    blowingFrom: "Blowing from",
    degrees: "degrees",
    windHint: "270 = from the west",
    kindOfChange: "Kind of change",
    closeRoad: "Close a road",
    publicEvent: "Public event",
    roadworks: "Roadworks",
    street: "Street",
    egCorso: "e.g. Via del Corso",
    attending: "People attending",
    lanesClosed: "Lanes closed",
    emergencyService: "Emergency service",
    streetToClose: "Street to close",
    egOstiense: "e.g. Via Ostiense",
    floodSameTime: "River flood at the same time, optional",
    mRise: "m rise",
    floodHint: "Flooded streets are closed too. Leave empty to ignore.",
    antenna: "antenna",
    height: "Height above ground",
    band: "Frequency band",
    noSpread: "no spread",
    na: "n/a",
    whatIf: "what-if",
    nothingComputed: "Nothing was computed for this run.",
    measuredAs: (m: string) => `Measured as: ${m}`,
    notAvailableTitle: "Not available for this run",
    todayBaseline: "Today (baseline)",
    withChange: "With the change",
    todayAndChange: "Today and with the change",
    measure: "Measure",
    today: "Today",
    difference: "Difference",
    rangeHint: "Middle value, with the 5th to 95th percentile range under it. Estimates, not measurements.",
    baselineAndChange: "Baseline and change",
    withChangeVariant: "With the change (variant)",
    sameScale: "Same scale for both bars. Band = 5th to 95th percentile, line = middle value. Estimates, not measurements.",
    otherFigures: "Other figures",
    estimatesHint: "Estimates, not measurements: read every figure with its range.",
    andMore: (n: number) => `and ${n} more`,
    details: "Details",
    noFigures: "The run returned no figures to show.",
    labTitle: "Scenario lab",
    labSubtitle: "Try a change on the city and compare it with today.",
    running: "Running…",
    runScenario: "Run scenario",
    footerHint: "Results compare today (baseline) with your change (variant) and always carry a range.",
    step1: "1 · Scenario",
    step2: "2 · Where",
    step3: "3 · What changes",
    smallerTitle: "Pick a smaller area",
    smallerBody: "This is a heavy simulation: it runs on a municipio, an urban zone or a drawn area. The tool will refuse larger areas.",
    drawSmallTitle: "Draw a small area",
    drawSmallBody:
      'Traffic is simulated street by street, so it runs on a few blocks only. Use "Draw an area on the map" around the street or the event. The tool refuses a larger area and tells you its limit.',
    result: "Result",
    closeResult: "Close result",
    runningScenario: "Running the scenario…",
    runFailed: "The run failed",
    addPoints: " · click the map to add points",
    movePoint: " · click the map to move the point",
    placeIt: " · click the map to place it",
    onMap: "On the map",
    yourChange: "Your change (what-if)",
    likelyExtent: "Likely extent (P50)",
    possibleExtent: "Possible extent (P95)",
    placesListed: "Places listed in the result",
    whatIfNote: "What-if result: an estimate, not a measured event.",
    showResult: "Show result",
    placeCategory: "Place in the result",
    listedIn: "Listed in",
    position: "Position",
    yourPoint: "Your point (what-if)",
    yourPointNote: "The place you chose for the change",
  },
  it: {
    clickMove: (what: string) => `Clicca sulla mappa per spostare ${what}`,
    clickPlace: (what: string) => `Clicca sulla mappa per indicare ${what}`,
    longitude: "Longitudine",
    latitude: "Latitudine",
    howRiver: "Come impostare il fiume",
    returnPeriod: "Piena storica",
    floodSize: "Grandezza della piena",
    yearFlood: (y: string) =>
      y === "200"
        ? "Piena duecentennale (pericolosità media ufficiale)"
        : y === "500"
          ? "Piena cinquecentennale (mappa ufficiale delle piene rare)"
          : `Piena con tempo di ritorno ${y} anni`,
    returnPeriodHint:
      "Scenario, non previsione: la piena del Tevere attesa in media una volta ogni tanti anni (portata ufficiale a Ripetta). La piena del 1937 era circa cinquantennale.",
    rise: "Aumento",
    gaugeLevel: "Livello idrometro",
    forecast: "Previsione",
    riverGauge: "Idrometro del fiume",
    waterLevel: "Livello dell'acqua all'idrometro",
    riverForecastHint: "Usa il livello più alto della previsione del fiume per i prossimi giorni.",
    riverRise: "Aumento del fiume sopra il normale",
    rainSource: "Da dove viene la pioggia",
    amount: "Quantità",
    radarNow: "Radar adesso",
    rain: "Pioggia",
    over: "In",
    hours: "ore",
    radarHint: "Usa la pioggia che il radar vede adesso.",
    rainForecastHint: "Usa la previsione della pioggia.",
    highRiver: "Fiume in piena, facoltativo",
    eg3: "es. 3",
    highRiverHint: "Un Tevere alto blocca gli scarichi delle fognature. Lascia vuoto per ignorarlo.",
    temperatures: "Temperature",
    enterValues: "Inserisci i valori",
    dayMax: "Massima di giorno",
    nightMin: "Minima di notte",
    tempForecastHint: "Usa la previsione delle temperature per l'area.",
    changesToTest: "Modifiche da provare, facoltativo",
    treeCover: "Verde aggiunto",
    sealed: "Suolo impermeabile rimosso",
    eg10: "es. 10",
    releaseWhere: "Dove avviene il rilascio",
    pointOnMap: "Punto sulla mappa",
    namedSite: "Sito con nome",
    hazardousSite: "Sito a rischio",
    siteHint: "Nome di un sito a rischio (Seveso) in elenco.",
    releasePoint: "il punto del rilascio",
    substance: "Sostanza",
    releaseRate: "Portata del rilascio",
    wind: "Vento",
    windForecast: "Previsione del vento",
    enterWind: "Inserisci il vento",
    windSpeed: "Velocità del vento",
    blowingFrom: "Soffia da",
    degrees: "gradi",
    windHint: "270 = da ovest",
    kindOfChange: "Tipo di modifica",
    closeRoad: "Chiudi una strada",
    publicEvent: "Evento pubblico",
    roadworks: "Cantiere",
    street: "Strada",
    egCorso: "es. Via del Corso",
    attending: "Persone presenti",
    lanesClosed: "Corsie chiuse",
    emergencyService: "Servizio di soccorso",
    streetToClose: "Strada da chiudere",
    egOstiense: "es. Via Ostiense",
    floodSameTime: "Piena del fiume nello stesso momento, facoltativo",
    mRise: "m di aumento",
    floodHint: "Anche le strade allagate sono chiuse. Lascia vuoto per ignorarlo.",
    antenna: "l'antenna",
    height: "Altezza da terra",
    band: "Banda di frequenza",
    noSpread: "nessuna variazione",
    na: "n.d.",
    whatIf: "ipotesi",
    nothingComputed: "Per questa esecuzione non è stato calcolato nulla.",
    measuredAs: (m: string) => `Misurato come: ${m}`,
    notAvailableTitle: "Non disponibile per questa esecuzione",
    todayBaseline: "Oggi",
    withChange: "Con la modifica",
    todayAndChange: "Oggi e con la modifica",
    measure: "Misura",
    today: "Oggi",
    difference: "Differenza",
    rangeHint: "Valore centrale, con sotto l'intervallo dal 5º al 95º percentile. Stime, non misure.",
    baselineAndChange: "Oggi e con la modifica",
    withChangeVariant: "Con la modifica",
    sameScale: "Stessa scala per le due barre. Fascia = dal 5º al 95º percentile, linea = valore centrale. Stime, non misure.",
    otherFigures: "Altri valori",
    estimatesHint: "Stime, non misure: leggi ogni valore insieme al suo intervallo.",
    andMore: (n: number) => `e altre ${n}`,
    details: "Dettagli",
    noFigures: "L'esecuzione non ha restituito valori da mostrare.",
    labTitle: "Laboratorio di scenari",
    labSubtitle: "Prova una modifica sulla città e confrontala con oggi.",
    running: "In corso…",
    runScenario: "Avvia scenario",
    footerHint: "I risultati confrontano oggi con la tua modifica e hanno sempre un intervallo.",
    step1: "1 · Scenario",
    step2: "2 · Dove",
    step3: "3 · Cosa cambia",
    smallerTitle: "Scegli un'area più piccola",
    smallerBody: "È una simulazione pesante: funziona su un municipio, una zona urbanistica o un'area disegnata. Lo strumento rifiuta le aree più grandi.",
    drawSmallTitle: "Disegna un'area piccola",
    drawSmallBody:
      'Il traffico è simulato strada per strada, quindi funziona solo su pochi isolati. Usa "Disegna un\'area sulla mappa" intorno alla strada o all\'evento. Lo strumento rifiuta un\'area più grande e ti dice il suo limite.',
    result: "Risultato",
    closeResult: "Chiudi il risultato",
    runningScenario: "Scenario in corso…",
    runFailed: "L'esecuzione non è riuscita",
    addPoints: " · clicca sulla mappa per aggiungere punti",
    movePoint: " · clicca sulla mappa per spostare il punto",
    placeIt: " · clicca sulla mappa per indicarlo",
    onMap: "Sulla mappa",
    yourChange: "La tua modifica (ipotesi)",
    likelyExtent: "Estensione probabile (P50)",
    possibleExtent: "Estensione possibile (P95)",
    placesListed: "Luoghi elencati nel risultato",
    whatIfNote: "Risultato di un'ipotesi: una stima, non un evento misurato.",
    showResult: "Mostra il risultato",
    placeCategory: "Luogo nel risultato",
    listedIn: "Elencato in",
    position: "Posizione",
    yourPoint: "Il tuo punto (ipotesi)",
    yourPointNote: "Il luogo che hai scelto per la modifica",
  },
});

const ICONS: Record<ScenarioTile, LucideIcon> = {
  river_flood: Waves,
  rain_flood: CloudRain,
  heatwave: ThermometerSun,
  chemical_plume: Biohazard,
  road_closure: TrafficCone,
  emergency_access: Siren,
  antenna: RadioTower,
  population_exposure: Users,
};

type Form = Record<string, string>;
type Rgb = [number, number, number];
const rgb = (c: Rgb, a = 1) => `rgb(${c.join(" ")} / ${a})`;

const initialForms = () => Object.fromEntries(SCENARIOS.map((s) => [s.id, { ...s.defaults }])) as Record<ScenarioTile, Form>;

/** Badge picture for a place in a result, from the name of the table that lists it (English or Italian). */
const PLACE_GLYPHS: [RegExp, Glyph][] = [
  [/hospital|ospedal|emergenc|pronto soccorso/i, "hospital"],
  [/school|scuol|nursery|nido|infanzia/i, "school"],
  [/care|cura|riposo|health|sanitar/i, "care"],
  [/playground|giochi/i, "play"],
  [/overflow|tracim|sewer|fogn|flood|alluvion|esondaz|allagam|water|acqua/i, "flood"],
  [/antenna|mast|impianto radio/i, "antenna"],
  [/road|strad|street|via |edge|traffic|traffico/i, "traffic"],
  [/bus|tram|stop|fermat/i, "bus"],
  [/sport|gym|palestr/i, "sport"],
  [/museum|museo|gallery|galleri/i, "museum"],
];
function placeGlyph(table: string): Glyph {
  return PLACE_GLYPHS.find(([re]) => re.test(table))?.[1] ?? "pin";
}

function placeResource(p: PlaceItem): Resource {
  const t = tr(T);
  return {
    glyph: placeGlyph(p.table),
    title: p.label,
    category: t.placeCategory,
    readings: [],
    facts: [
      { label: t.listedIn, value: p.table },
      { label: t.position, value: `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}` },
    ],
    extra: [],
    synthetic: false,
    position: [p.lon, p.lat],
  };
}

/** Point placed by the officer, when the kind needs one and the form holds valid coordinates. */
function placedPoint(tile: ScenarioTile, f: Form): [number, number] | null {
  if (!scenarioSpec(tile).usesPoint || (tile === "chemical_plume" && f.place === "site")) return null;
  const lon = Number(f.lon);
  const lat = Number(f.lat);
  return f.lon?.trim() && f.lat?.trim() && Number.isFinite(lon) && Number.isFinite(lat) ? [lon, lat] : null;
}

// --- Small form pieces ------------------------------------------------------------------------------------

function NumField({ label, unit, value, onChange, hint, placeholder }: { label: string; unit?: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string }) {
  return (
    <Field label={unit ? `${label} (${unit})` : label} hint={hint}>
      <input className="input num" inputMode="decimal" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function TextField({ label, value, onChange, hint, placeholder, list }: { label: string; value: string; onChange: (v: string) => void; hint?: ReactNode; placeholder?: string; list?: string }) {
  return (
    <Field label={label} hint={hint}>
      <input className="input" value={value} placeholder={placeholder} list={list} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

function PointFields({ f, set, what }: { f: Form; set: (k: string, v: string) => void; what: string }) {
  const t = tr(T);
  const placed = f.lon?.trim() && f.lat?.trim();
  return (
    <div className="space-y-2 rounded border border-dashed border-whatif/60 bg-whatif/5 p-2.5">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-whatif">
        <Crosshair className="h-3.5 w-3.5" aria-hidden="true" />
        {placed ? t.clickMove(what) : t.clickPlace(what)}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <NumField label={t.longitude} value={f.lon ?? ""} onChange={(v) => set("lon", v)} placeholder="12.4833" />
        <NumField label={t.latitude} value={f.lat ?? ""} onChange={(v) => set("lat", v)} placeholder="41.9009" />
      </div>
    </div>
  );
}

function ChangeForm({ tile, f, set }: { tile: ScenarioTile; f: Form; set: (k: string, v: string) => void }) {
  const t = tr(T);
  const two = "grid grid-cols-2 gap-2";
  switch (tile) {
    case "river_flood":
      return (
        <>
          <Segmented
            label={t.howRiver}
            value={(f.mode ?? "return") as "return" | "rise" | "level" | "forecast"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "return", label: t.returnPeriod },
              { id: "rise", label: t.rise },
              { id: "level", label: t.gaugeLevel },
              { id: "forecast", label: t.forecast },
            ]}
          />
          {f.mode === "level" || f.mode === "forecast" ? (
            <Field label={t.riverGauge}>
              <select className="input" value={f.gauge} onChange={(e) => set("gauge", e.target.value)}>
                {SCENARIO_GAUGES.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.label}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          {f.mode === "level" && <NumField label={t.waterLevel} unit="m" value={f.level_m ?? ""} onChange={(v) => set("level_m", v)} />}
          {f.mode === "forecast" && <p className="hint">{t.riverForecastHint}</p>}
          {(f.mode ?? "return") === "return" && (
            <>
              <Field label={t.floodSize}>
                <select className="input" value={f.return_period ?? "500"} onChange={(e) => set("return_period", e.target.value)}>
                  {["50", "100", "200", "500"].map((y) => (
                    <option key={y} value={y}>
                      {t.yearFlood(y)}
                    </option>
                  ))}
                </select>
              </Field>
              <p className="hint">{t.returnPeriodHint}</p>
            </>
          )}
          {f.mode === "rise" && (
            <NumField label={t.riverRise} unit="m" value={f.rise_m ?? ""} onChange={(v) => set("rise_m", v)} />
          )}
        </>
      );
    case "rain_flood":
      return (
        <>
          <Segmented
            label={t.rainSource}
            value={(f.mode ?? "rain") as "rain" | "radar" | "forecast"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "rain", label: t.amount },
              { id: "radar", label: t.radarNow },
              { id: "forecast", label: t.forecast },
            ]}
          />
          {(f.mode ?? "rain") === "rain" ? (
            <div className={two}>
              <NumField label={t.rain} unit="mm" value={f.rain_mm ?? ""} onChange={(v) => set("rain_mm", v)} />
              <NumField label={t.over} unit={t.hours} value={f.duration_h ?? ""} onChange={(v) => set("duration_h", v)} />
            </div>
          ) : (
            <p className="hint">{f.mode === "radar" ? t.radarHint : t.rainForecastHint}</p>
          )}
          <NumField
            label={t.highRiver}
            unit="m"
            value={f.river_rise_m ?? ""}
            onChange={(v) => set("river_rise_m", v)}
            placeholder={t.eg3}
            hint={t.highRiverHint}
          />
        </>
      );
    case "heatwave":
      return (
        <>
          <Segmented
            label={t.temperatures}
            value={(f.temperature ?? "forecast") as "forecast" | "manual"}
            onChange={(v) => set("temperature", v)}
            options={[
              { id: "forecast", label: t.forecast },
              { id: "manual", label: t.enterValues },
            ]}
          />
          {f.temperature === "manual" ? (
            <div className={two}>
              <NumField label={t.dayMax} unit="°C" value={f.tmax_c ?? ""} onChange={(v) => set("tmax_c", v)} />
              <NumField label={t.nightMin} unit="°C" value={f.tmin_c ?? ""} onChange={(v) => set("tmin_c", v)} />
            </div>
          ) : (
            <p className="hint">{t.tempForecastHint}</p>
          )}
          <div className="label pt-1">{t.changesToTest}</div>
          <div className={two}>
            <NumField label={t.treeCover} unit="%" value={f.trees_pct ?? ""} onChange={(v) => set("trees_pct", v)} placeholder={t.eg10} />
            <NumField label={t.sealed} unit="%" value={f.depave_pct ?? ""} onChange={(v) => set("depave_pct", v)} placeholder={t.eg10} />
          </div>
        </>
      );
    case "chemical_plume":
      return (
        <>
          <Segmented
            label={t.releaseWhere}
            value={(f.place ?? "point") as "point" | "site"}
            onChange={(v) => set("place", v)}
            options={[
              { id: "point", label: t.pointOnMap },
              { id: "site", label: t.namedSite },
            ]}
          />
          {f.place === "site" ? (
            <TextField label={t.hazardousSite} value={f.site ?? ""} onChange={(v) => set("site", v)} hint={t.siteHint} />
          ) : (
            <PointFields f={f} set={set} what={tr(T).releasePoint} />
          )}
          <div className={two}>
            <TextField label={t.substance} value={f.substance ?? ""} onChange={(v) => set("substance", v)} list="scenario-substances" />
            <NumField label={t.releaseRate} unit="kg/s" value={f.release_kg_s ?? ""} onChange={(v) => set("release_kg_s", v)} />
          </div>
          <datalist id="scenario-substances">
            {SCENARIO_SUBSTANCES.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <Segmented
            label={t.wind}
            value={(f.wind ?? "forecast") as "forecast" | "manual"}
            onChange={(v) => set("wind", v)}
            options={[
              { id: "forecast", label: t.windForecast },
              { id: "manual", label: t.enterWind },
            ]}
          />
          {f.wind === "manual" && (
            <div className={two}>
              <NumField label={t.windSpeed} unit="m/s" value={f.wind_speed_ms ?? ""} onChange={(v) => set("wind_speed_ms", v)} />
              <NumField label={t.blowingFrom} unit={t.degrees} value={f.wind_from_deg ?? ""} onChange={(v) => set("wind_from_deg", v)} hint={t.windHint} />
            </div>
          )}
        </>
      );
    case "road_closure":
      return (
        <>
          <Segmented
            label={t.kindOfChange}
            value={(f.mode ?? "close") as "close" | "event" | "roadworks"}
            onChange={(v) => set("mode", v)}
            options={[
              { id: "close", label: t.closeRoad },
              { id: "event", label: t.publicEvent },
              { id: "roadworks", label: t.roadworks },
            ]}
          />
          <TextField label={t.street} value={f.street ?? ""} onChange={(v) => set("street", v)} placeholder={t.egCorso} />
          {f.mode === "event" && <NumField label={t.attending} value={f.attendees ?? ""} onChange={(v) => set("attendees", v)} />}
          {f.mode === "roadworks" && <NumField label={t.lanesClosed} value={f.lanes_closed ?? ""} onChange={(v) => set("lanes_closed", v)} />}
        </>
      );
    case "emergency_access":
      return (
        <>
          <Segmented
            label={t.emergencyService}
            value={(f.service ?? "fire") as "fire" | "ambulance" | "police"}
            onChange={(v) => set("service", v)}
            options={SCENARIO_SERVICES.map((s) => ({ id: s.id, label: s.label }))}
          />
          <TextField label={t.streetToClose} value={f.street ?? ""} onChange={(v) => set("street", v)} placeholder={t.egOstiense} />
          <NumField
            label={t.floodSameTime}
            unit={t.mRise}
            value={f.flood_rise_m ?? ""}
            onChange={(v) => set("flood_rise_m", v)}
            placeholder={t.eg3}
            hint={t.floodHint}
          />
        </>
      );
    case "antenna":
    case "population_exposure":
      return (
        <>
          <PointFields f={f} set={set} what={tr(T).antenna} />
          <div className={two}>
            <NumField label={t.height} unit="m" value={f.height_m ?? ""} onChange={(v) => set("height_m", v)} />
            <Field label={t.band}>
              <select className="input" value={f.band ?? "3500"} onChange={(e) => set("band", e.target.value)}>
                {SCENARIO_BANDS.map((b) => (
                  <option key={b} value={b}>
                    {b} MHz
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </>
      );
  }
}

// --- Result pieces ----------------------------------------------------------------------------------------

const rangeNote = (q: Quantile) => rangeText(q);

/** One table cell: the middle value, with the range under it. `signed` marks an increase with a plus. */
function QuantileCell({ q, tone = "", signed = false }: { q: Quantile | null; tone?: string; signed?: boolean }) {
  if (!q) return <td className="text-muted">{tr(T).na}</td>;
  const plus = signed && q.p50 > 0 ? "+" : "";
  return (
    <td>
      <span className={`num font-semibold ${tone}`}>
        {plus}
        {fmtNumber(q.p50)}
      </span>
      <span className="block whitespace-nowrap text-2xs text-muted">{q.p5 === q.p95 ? tr(T).noSpread : `${fmtNumber(q.p5)}–${fmtNumber(q.p95)}`}</span>
    </td>
  );
}

function ResultView({ env, title }: { env: Envelope<ScenarioResult>; title: string }) {
  const t = tr(T);
  const s = useMemo(() => summariseScenario(env.result), [env]);
  // A nested pair (e.g. residents beyond the target time) carries its own meaning; the top-level one uses `unit`.
  const unit = s.compare?.path ? unitFor(s.compare.path) : (env.result.unit ?? "");
  // People and extent first; what is shown as a key figure is not repeated further down.
  const headline = useMemo(() => keyFigures(s), [s]);
  const shown = new Set(headline.map((f) => f.path));
  const rest = s.quantiles.filter((q) => !shown.has(q.path));
  const facts = s.facts.filter((f) => !shown.has(f.path));
  const max = s.compare ? Math.max(s.compare.baseline.p95, s.compare.variant.p95, 1e-9) * 1.1 : 1;
  const nothing = !s.compare && !s.quantiles.length && !s.facts.length && !s.tables.length && !s.footprints.length;

  // A refused or not-available run: RunMeta already shows the reason as a callout, so show nothing else.
  if (env.status && env.status !== "ok") {
    return (
      <div className="animate-rise-in space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-bold">{title}</h2>
          <KindBadge kind="simulated" text={t.whatIf} />
        </div>
        <p className="hint">{t.nothingComputed}</p>
        <RunMeta env={env} />
      </div>
    );
  }

  return (
    <div className="animate-rise-in space-y-5">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-bold">{title}</h2>
          <KindBadge kind="simulated" text={t.whatIf} />
        </div>
        {(s.compare?.label ?? env.result.metric) && <p className="hint">{t.measuredAs(String(s.compare?.label ?? env.result.metric))}</p>}
      </div>

      {s.notAvailable && (
        <Callout tone="warn" title={t.notAvailableTitle}>
          {s.notAvailable}
        </Callout>
      )}

      {s.compare && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label={t.todayBaseline} value={fmtNumber(s.compare.baseline.p50)} unit={unit} note={rangeNote(s.compare.baseline)} />
          <Stat label={t.withChange} value={fmtNumber(s.compare.variant.p50)} unit={unit} note={rangeNote(s.compare.variant)} tone="whatif" />
        </div>
      )}
      {headline.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {headline.map((q) => (
            <Stat key={q.path} label={q.label} value={q.value} unit={q.unit} note={q.note} />
          ))}
        </div>
      )}

      {s.comparisons.length > 0 && (
        <Section title={t.todayAndChange}>
          <div className="overflow-x-auto rounded border border-line">
            <table className="table text-xs">
              <thead>
                <tr>
                  <th scope="col">{t.measure}</th>
                  <th scope="col">{t.today}</th>
                  <th scope="col">{t.withChange}</th>
                  <th scope="col">{t.difference}</th>
                </tr>
              </thead>
              <tbody>
                {s.comparisons.map((c) => (
                  <tr key={c.path}>
                    <th scope="row" className="text-left font-semibold">
                      {c.label}
                      {c.unit && <span className="font-normal text-muted"> ({c.unit})</span>}
                    </th>
                    <QuantileCell q={c.baseline} />
                    <QuantileCell q={c.variant} tone="text-whatif" />
                    <QuantileCell q={c.difference} signed />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">{t.rangeHint}</p>
        </Section>
      )}

      {s.compare && s.comparisons.length === 0 && (
        <Section title={s.compare.label ?? t.baselineAndChange}>
          <RangeBar label={t.todayBaseline} e={{ ...s.compare.baseline, calibration: env.result.baseline?.calibration }} unit={unit} max={max} note={false} />
          <RangeBar label={t.withChangeVariant} e={s.compare.variant} unit={unit} max={max} tone="whatif" note={false} />
          <p className="hint">{t.sameScale}</p>
        </Section>
      )}

      {rest.length > 0 && (
        <Section title={t.otherFigures}>
          {/* A bar only says something when there is a spread; single values go in tiles. */}
          {rest.some((q) => q.value.p5 === q.value.p95) && (
            <div className="grid grid-cols-2 gap-2">
              {rest
                .filter((q) => q.value.p5 === q.value.p95)
                .map((q) => (
                  <Stat key={q.path} label={q.label} value={fmtNumber(q.value.p50)} unit={q.unit} note={rangeNote(q.value)} />
                ))}
            </div>
          )}
          {rest
            .filter((q) => q.value.p5 !== q.value.p95)
            .map((q) => (
              <RangeBar key={q.path} label={q.label} e={q.value} unit={q.unit} max={Math.max(q.value.p95, 1e-9) * 1.15} note={false} />
            ))}
        </Section>
      )}
      {!s.compare && s.quantiles.length > 0 && <p className="hint">{t.estimatesHint}</p>}

      {s.tables.map((tb) => (
        <Section key={tb.path} title={`${tb.label} (${tb.total})`}>
          <div className="overflow-x-auto rounded border border-line">
            <table className="table text-xs">
              <thead>
                <tr>
                  {tb.columns.map((c) => (
                    <th key={c} scope="col" className="align-bottom">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tb.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td
                        key={j}
                        // Long notes get a readable column width instead of one word per line.
                        className={/^[\d\-—]/.test(c) ? "num whitespace-nowrap" : c.length > 28 ? "min-w-[14rem] break-words" : "break-words"}
                      >
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {tb.total > MAX_ROWS && <p className="hint">{t.andMore(tb.total - MAX_ROWS)}</p>}
        </Section>
      ))}

      {facts.length > 0 && (
        <Section title={t.details}>
          <dl className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-1.5 text-xs">
            {facts.map((f) => (
              <Fragment key={f.path}>
                <dt className="text-muted">{f.label}</dt>
                <dd className={`break-words text-ink ${/^[\d\-]/.test(f.value) ? "num" : ""}`}>{f.value}</dd>
              </Fragment>
            ))}
          </dl>
        </Section>
      )}

      {nothing && !s.notAvailable && <p className="hint">{t.noFigures}</p>}

      <div className="border-t border-line pt-3">
        <RunMeta env={env} />
      </div>
    </div>
  );
}

// --- Screen -----------------------------------------------------------------------------------------------

export default function ScenarioLab() {
  const t = tr(T);
  const { run } = useSession();
  const { palette } = useTheme();
  const [tile, setTile] = useState<ScenarioTile>("river_flood");
  const [forms, setForms] = useState<Record<ScenarioTile, Form>>(initialForms);
  const [area, setArea] = useState<Area>({ type: "municipio", id: "1" });
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<number[][]>([]);
  const [env, setEnv] = useState<Envelope<ScenarioResult> | null>(null);
  const [ran, setRan] = useState<{ title: string; area: string; tile: ScenarioTile; point: [number, number] | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  /** Zoom in quarter steps: the 3D markers keep their size on screen with it. */
  const [zoom, setZoom] = useState(TWIN_START_ZOOM);
  const [hover, setHover] = useState<{ x: number; y: number; id: string; resource: Resource } | null>(null);
  /** The place of the result whose card is open (after a click or tap). */
  const [picked, setPicked] = useState<{ id: string; place: PlaceItem } | null>(null);
  const [camera, setCamera] = useState<MapFocus | null>(null);

  const spec = scenarioSpec(tile);
  const f = forms[tile];
  const kind = resolveKind(tile, f);
  const problem = changeProblem(kind, f);
  const point = placedPoint(tile, f);
  const set = (k: string, v: string) => setForms((all) => ({ ...all, [tile]: { ...all[tile], [k]: v } }));

  async function go() {
    setBusy(true);
    setShowResult(true);
    setError(null);
    setEnv(null);
    setPicked(null);
    setCamera(null);
    setRan({ title: spec.label, area: areaLabel(area), tile, point });
    try {
      const c = buildScenarioChange(kind, f);
      setEnv(await run<ScenarioResult>("run_scenario", { kind, area: areaToArg(area), change: c }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const toggleDraw = () => {
    if (drawing && draft.length >= 3) {
      setArea({ type: "polygon", geometry: { type: "Polygon", coordinates: [[...draft, draft[0]!]] } });
      setDraft([]);
    } else if (!drawing) setDraft([]);
    setDrawing(!drawing);
  };

  const onMapClick = (p: { lon: number; lat: number }) => {
    if (drawing) return setDraft((d) => [...d, [p.lon, p.lat]]);
    // A click on a marker opens its card; it does not move the point.
    if (hover) return;
    if (!spec.usesPoint || (tile === "chemical_plume" && f.place === "site")) return;
    setForms((all) => ({ ...all, [tile]: { ...all[tile], lon: p.lon.toFixed(5), lat: p.lat.toFixed(5) } }));
  };

  const summary = useMemo(() => (env ? summariseScenario(env.result) : null), [env]);
  const placeMarkers = useMemo<Marker<PlaceItem>[]>(
    () =>
      (summary?.points ?? []).map((p, i) => ({
        id: `${i}-${p.lon.toFixed(6)},${p.lat.toFixed(6)}`,
        position: [p.lon, p.lat],
        color: palette.point,
        level: null,
        glyph: placeGlyph(p.table),
        data: p,
      })),
    [summary, palette],
  );
  const group = ran ? scenarioSpec(ran.tile).group : spec.group;
  const footColor: Rgb = group === "Water" ? palette.accent : group === "Heat" || group === "Hazard" ? palette.bad : palette.whatIf;

  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (area.type === "polygon" || draft.length) {
      const ring = area.type === "polygon" && !drawing ? area.geometry.coordinates[0]! : draft;
      out.push(
        new PolygonLayer({
          id: "scenario-area",
          data: [{ ring }],
          getPolygon: (d: { ring: number[][] }) => d.ring,
          getFillColor: [...palette.accent, 20],
          getLineColor: [...palette.accent, 255],
          lineWidthMinPixels: 2,
          updateTriggers: { getFillColor: palette.accent, getLineColor: palette.accent },
        }),
        new ScatterplotLayer({
          id: "scenario-area-pts",
          data: drawing ? draft : [],
          getPosition: (p: number[]) => p as [number, number],
          getFillColor: palette.accent,
          radiusMinPixels: 4,
          updateTriggers: { getFillColor: palette.accent },
        }),
      );
    }
    if (summary) {
      // Possible (P95) first, so the likely (P50) footprint sits on top and reads stronger.
      const ordered = [...summary.footprints].sort((a, b) => (a.level === b.level ? 0 : a.level === "possible" ? -1 : 1));
      ordered.forEach((fp, i) => {
        const likely = fp.level === "likely";
        out.push(
          new GeoJsonLayer({
            id: `scenario-footprint-${i}-${fp.path}`,
            data: { type: "Feature", properties: {}, geometry: fp.geometry } as never,
            filled: true,
            stroked: true,
            getFillColor: [...footColor, likely ? 70 : 30],
            getLineColor: [...footColor, likely ? 255 : 150],
            getLineWidth: likely ? 2 : 1,
            lineWidthUnits: "pixels",
            updateTriggers: { getFillColor: footColor, getLineColor: footColor },
          }),
        );
      });
      // Places the result lists: one 3D marker each on the city model, with a badge for the kind of place.
      out.push(...markerLayers(placeMarkers, { id: "plc", zoom, palette, selectedId: picked?.id ?? null, hoveredId: hover?.id }));
    }
    if (point) {
      // The officer's what-if point: a marker in the what-if colour.
      out.push(
        ...markerLayers([{ id: "point", position: point, color: palette.whatIf, level: null, glyph: "pin", data: point }], {
          id: "spt",
          zoom,
          palette,
          hoveredId: hover?.id,
        }),
      );
    }
    return out;
  }, [area, draft, drawing, summary, placeMarkers, point, palette, footColor, zoom, picked?.id, hover?.id]);

  const onHover = (info: PickingInfo) => {
    const place = pickedMarker<PlaceItem>(info, "plc");
    if (place) return setHover({ x: info.x, y: info.y, id: place.id, resource: placeResource(place.data) });
    const pt = pickedMarker<[number, number]>(info, "spt");
    if (pt)
      return setHover({
        x: info.x,
        y: info.y,
        id: pt.id,
        resource: {
          glyph: "pin",
          title: t.yourPoint,
          category: t.yourPointNote,
          readings: [],
          facts: [{ label: t.position, value: `${pt.data[1].toFixed(5)}, ${pt.data[0].toFixed(5)}` }],
          extra: [],
          synthetic: false,
          position: pt.data,
        },
      });
    setHover(null);
  };
  const onPick = (info: PickingInfo) => {
    if (drawing) return;
    const place = pickedMarker<PlaceItem>(info, "plc");
    setPicked(place ? { id: place.id, place: place.data } : null);
    setHover(null);
  };
  const detail = picked ? placeResource(picked.place) : null;

  // Frame the whole result once it arrives (not on every edit): all footprints, else the placed point.
  const focus = useMemo<MapFocus | null>(() => {
    const box = summary ? boundsOf(summary.footprints.map((f) => f.geometry)) : null;
    if (box) return { bounds: box, pitch: 25 };
    const p = summary ? ran?.point : null;
    return p ? { lon: p[0], lat: p[1], zoom: 15 } : null;
  }, [summary, ran]);

  const smallOnly = needsSmallArea(kind);
  const heavyWarn = !smallOnly && isHeavy(kind) && area.type === "city";
  const smallWarn = smallOnly && area.type !== "polygon";
  const likelyFp = summary?.footprints.filter((x) => x.level === "likely") ?? [];
  const possibleFp = summary?.footprints.filter((x) => x.level === "possible") ?? [];

  const panel = (
    <Panel
      title={t.labTitle}
      icon={FlaskConical}
      width="w-[24rem]"
      subtitle={t.labSubtitle}
      footer={
        <div className="space-y-2">
          <button type="button" className="btn w-full" onClick={() => void go()} disabled={busy || !!problem}>
            {busy ? (
              <>
                <Spinner />
                {t.running}
              </>
            ) : (
              <>
                <Play className="h-4 w-4" aria-hidden="true" />
                {t.runScenario}
              </>
            )}
          </button>
          <p className="hint" role={problem ? "status" : undefined}>
            {problem ?? t.footerHint}
          </p>
        </div>
      }
    >
      <Section title={t.step1}>
        {/* Groups with one tile share a row, so the whole catalogue fits above the fold. */}
        <div className="grid grid-cols-2 gap-x-1.5 gap-y-2.5">
          {SCENARIO_GROUPS.map((g) => {
            const tiles = SCENARIOS.filter((s) => s.group === g);
            return (
              <div key={g} className={`space-y-1 ${tiles.length > 1 ? "col-span-2" : ""}`} role="group" aria-label={groupLabel(g)}>
                <div className="text-2xs font-semibold uppercase tracking-[0.06em] text-muted">{groupLabel(g)}</div>
                <div className={`grid gap-1.5 ${tiles.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                  {tiles.map((s) => {
                    const Icon = ICONS[s.id];
                    const active = s.id === tile;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setTile(s.id)}
                        className={`flex h-full flex-col items-start gap-0.5 rounded border px-2 py-1.5 text-left transition-colors duration-150 ${
                          active ? "border-link bg-primary-soft text-link" : "border-line bg-surface text-ink hover:border-line-strong hover:bg-sunken"
                        }`}
                      >
                        <span className="flex items-start gap-1.5 text-sm font-semibold leading-tight">
                          <Icon className="mt-px h-4 w-4 shrink-0" aria-hidden="true" />
                          {s.label}
                        </span>
                        <span className={`text-2xs leading-snug ${active ? "text-ink" : "text-muted"}`}>{s.description}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title={t.step2}>
        <AreaPicker area={area} onChange={setArea} drawing={drawing} onDraw={toggleDraw} />
        {heavyWarn && (
          <Callout tone="warn" title={t.smallerTitle}>
            {t.smallerBody}
          </Callout>
        )}
        {smallWarn && (
          <Callout tone="warn" title={t.drawSmallTitle}>
            {t.drawSmallBody}
          </Callout>
        )}
      </Section>

      <Section title={t.step3}>
        <ChangeForm tile={tile} f={f} set={set} />
      </Section>
    </Panel>
  );

  const right =
    showResult && (busy || env || error) ? (
      <Panel
        side="right"
        width="w-[24rem]"
        title={t.result}
        subtitle={ran ? `${ran.title} · ${ran.area}` : undefined}
        actions={
          <button type="button" className="btn-quiet -mr-1 -mt-0.5" aria-label={t.closeResult} onClick={() => setShowResult(false)}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        }
      >
        {busy && (
          <div className="space-y-4" aria-live="polite">
            <p className="flex items-center gap-2 text-sm text-muted">
              <Spinner />
              {t.runningScenario}
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div className="skeleton h-16" />
              <div className="skeleton h-16" />
            </div>
            <Skeleton lines={6} />
          </div>
        )}
        {error && (
          <Callout tone="error" title={t.runFailed}>
            {error}
          </Callout>
        )}
        {env && ran && <ResultView env={env} title={ran.title} />}
      </Panel>
    ) : null;

  return (
    <Workspace panel={panel} right={right}>
      <CityMap
        layers={layers}
        initialZoom={12.5}
        pitch={35}
        focus={camera ?? focus}
        onZoomStep={setZoom}
        onHover={onHover}
        onPick={onPick}
        onClick={onMapClick}
      />
      {hover && <ResourceHover x={hover.x} y={hover.y} resource={hover.resource} />}
      {detail && (
        <ResourceDetail
          resource={detail}
          onClose={() => setPicked(null)}
          onZoomTo={() => setCamera({ lon: detail.position![0], lat: detail.position![1], zoom: 16.5, pitch: 60 })}
        />
      )}

      {!env && !busy && (
        <MapFloat position="top-left" className="max-w-[min(22rem,calc(100%-6rem))]">
          <div role="status" aria-live="polite" className="space-y-0.5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {(() => {
                const Icon = ICONS[tile];
                return <Icon className="h-4 w-4 text-link" aria-hidden="true" />;
              })()}
              {spec.label}
            </div>
            <div className="text-xs text-muted">
              {areaLabel(area)}
              {drawing
                ? t.addPoints
                : spec.usesPoint && !(tile === "chemical_plume" && f.place === "site")
                  ? point
                    ? t.movePoint
                    : t.placeIt
                  : ""}
            </div>
          </div>
        </MapFloat>
      )}

      {(point || likelyFp.length > 0 || possibleFp.length > 0 || (summary?.points.length ?? 0) > 0) && (
        <MapFloat position="bottom-left" className="w-60">
          <div className="space-y-1.5 text-xs">
            <div className="label">{t.onMap}</div>
            {point && (
              <LegendRow swatch={<span className="block h-3 w-3 rotate-45 border-2 border-dashed" style={{ borderColor: rgb(palette.whatIf), background: rgb(palette.whatIf, 0.25) }} />}>
                {t.yourChange}
              </LegendRow>
            )}
            {likelyFp.length > 0 && (
              <LegendRow swatch={<span className="block h-3 w-4 rounded-sm border-2" style={{ borderColor: rgb(footColor), background: rgb(footColor, 0.5) }} />}>
                {t.likelyExtent}
              </LegendRow>
            )}
            {possibleFp.length > 0 && (
              <LegendRow swatch={<span className="block h-3 w-4 rounded-sm border" style={{ borderColor: rgb(footColor, 0.6), background: rgb(footColor, 0.16) }} />}>
                {t.possibleExtent}
              </LegendRow>
            )}
            {(summary?.points.length ?? 0) > 0 && (
              <LegendRow swatch={<span className="block h-2.5 w-2.5 rounded-full" style={{ background: rgb(palette.point) }} />}>
                {t.placesListed}
              </LegendRow>
            )}
            {summary && (likelyFp.length > 0 || possibleFp.length > 0) && <p className="hint">{t.whatIfNote}</p>}
          </div>
        </MapFloat>
      )}

      {env && !showResult && (
        <div className="absolute right-14 top-3 z-10">
          <button type="button" className="btn-ghost btn-sm shadow-float" onClick={() => setShowResult(true)}>
            <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
            {t.showResult}
          </button>
        </div>
      )}

    </Workspace>
  );
}

function LegendRow({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex w-4 shrink-0 justify-center" aria-hidden="true">
        {swatch}
      </span>
      <span>{children}</span>
    </div>
  );
}
