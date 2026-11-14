// Ambiente: "how is the air here?" and "what is the electromagnetic field here?".
// The resident's position on top of the whole city, one value at a time, each with its level in plain words.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { KindBadge } from "@/components/Badge";
import { Chips, CitizenMap, HeatLegend, HereCard, MapScreen, PositionBar } from "@/components/CitizenMap";
import { GlyphIcon } from "@/components/MarkerCard";
import { LiveBadge } from "@/components/LiveBadge";
import { texts, tr } from "@/lib/i18n";
import { metricInfo } from "@/lib/layers";
import { useHeatmap, useHereAnswer } from "@/lib/useCitizenData";
import { usePosition } from "@/lib/usePosition";
import type { Glyph } from "@/map/markerGlyphs";

type LensId = "no2" | "pm10" | "pm25" | "o3" | "emf";

const LENSES: { id: LensId; layer: string; mode: "air" | "emf"; glyph: Glyph }[] = [
  { id: "no2", layer: "air_no2", mode: "air", glyph: "air" },
  { id: "pm10", layer: "air_pm10", mode: "air", glyph: "air" },
  { id: "pm25", layer: "air_pm25", mode: "air", glyph: "air" },
  { id: "o3", layer: "air_o3", mode: "air", glyph: "air" },
  { id: "emf", layer: "emf", mode: "emf", glyph: "field" },
];

const T = texts({
  en: {
    title: "Environment",
    lead: "The air and the electromagnetic fields where you are, on the map of Rome.",
    choose: "Value shown",
    emfChip: "Electromagnetic fields",
    what: {
      no2: "Nitrogen dioxide: a gas that comes mostly from traffic.",
      pm10: "PM10: dust and particles small enough to breathe in.",
      pm25: "PM2.5: the finest particles, from heating, traffic and smoke.",
      o3: "Ozone: forms in sunlight on warm days, highest in the afternoon.",
      emf: "Electric field from radio, TV and mobile phone antennas.",
    } as Record<LensId, string>,
    cityNow: "The whole city now",
    estimateNote: "Estimated by the city's digital twin from measuring stations and models. For information only.",
  },
  it: {
    title: "Ambiente",
    lead: "L'aria e i campi elettromagnetici dove sei, sulla mappa di Roma.",
    choose: "Valore mostrato",
    emfChip: "Campi elettromagnetici",
    what: {
      no2: "Biossido di azoto: un gas che viene soprattutto dal traffico.",
      pm10: "PM10: polveri abbastanza piccole da essere respirate.",
      pm25: "PM2.5: le polveri più sottili, da riscaldamento, traffico e fumo.",
      o3: "Ozono: si forma con il sole nelle giornate calde, più alto nel pomeriggio.",
      emf: "Campo elettrico delle antenne di radio, TV e telefonia mobile.",
    } as Record<LensId, string>,
    cityNow: "Tutta la città adesso",
    estimateNote: "Stima del gemello digitale della città da centraline e modelli. Solo a scopo informativo.",
  },
});

export default function Environment() {
  const t = tr(T);
  const [params, setParams] = useSearchParams();
  const view = params.get("vista") === "campi" ? "emf" : "air";
  const [lensId, setLensId] = useState<LensId>(view === "emf" ? "emf" : "no2");
  // A link from the home page ("Campi elettromagnetici qui") opens the matching value.
  useEffect(() => setLensId((cur) => (view === "emf" ? "emf" : cur === "emf" ? "no2" : cur)), [view]);
  const lens = LENSES.find((l) => l.id === lensId)!;
  const { position } = usePosition();
  const heat = useHeatmap(lens.layer);
  const here = useHereAnswer(lens.mode, lens.layer, position);
  const label = metricInfo(lens.layer).label;
  const unit = heat.status === "ok" ? heat.data.unit : "";
  const cityValues = useMemo(() => (heat.status === "ok" ? heat.data.cells.map((c) => c.value) : []), [heat]);
  const bands = heat.status === "ok" ? heat.data.legend : [];

  const pick = (id: LensId) => {
    setLensId(id);
    setParams({ vista: id === "emf" ? "campi" : "aria" }, { replace: true });
  };

  const sheet = (
    <>
      <Chips
        label={t.choose}
        value={lensId}
        onChange={pick}
        options={LENSES.map((l) => ({ id: l.id, label: l.id === "emf" ? t.emfChip : metricInfo(l.layer).label, glyph: l.glyph }))}
      />
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        <header className="flex items-start gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-real/10 text-real">
            <GlyphIcon glyph={lens.glyph} className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-base font-bold leading-tight">{lens.id === "emf" ? t.emfChip : `${label}`}</h1>
            <p className="hint mt-0.5">{t.what[lens.id]}</p>
          </div>
        </header>
        <PositionBar />
        <HereCard here={here} focusId={lens.id} onFocus={(id) => LENSES.some((l) => l.id === id) && pick(id as LensId)} cityValues={cityValues} bands={bands} />
        {heat.status === "ok" && (
          <section className="space-y-1.5 rounded border border-line px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="label">{t.cityNow}</h2>
              {heat.kind && <KindBadge kind={heat.kind} />}
            </div>
            <HeatLegend heat={heat.data} unit={unit} />
            {heat.live && <LiveBadge live={heat.live} />}
            <p className="hint">{t.estimateNote}</p>
          </section>
        )}
      </div>
    </>
  );

  return (
    <MapScreen sheet={sheet}>
      <CitizenMap heat={heat} heatLabel={label} unit={unit} />
    </MapScreen>
  );
}
