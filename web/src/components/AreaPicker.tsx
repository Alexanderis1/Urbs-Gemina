import { PenLine } from "lucide-react";
import { MUNICIPI, areaLabel, roman, type Area } from "@/lib/area";
import { Field } from "./ui";
import { texts, tr } from "@/lib/i18n";

const T = texts({
  en: {
    operatingArea: "Operating area",
    selected: (a: string) => `Selected: ${a}`,
    city: "Whole city",
    municipio: "Municipio",
    zoneOption: "Urban zone…",
    drawn: "Drawn area",
    zoneCode: "Urban zone code",
    zonePlaceholder: "Urban zone code, e.g. 1A",
    finish: "Finish drawing (click the map to add points)",
    draw: "Draw an area on the map",
  },
  it: {
    operatingArea: "Area operativa",
    selected: (a: string) => `Selezionata: ${a}`,
    city: "Tutta la città",
    municipio: "Municipio",
    zoneOption: "Zona urbanistica…",
    drawn: "Area disegnata",
    zoneCode: "Codice della zona urbanistica",
    zonePlaceholder: "Codice della zona urbanistica, es. 1A",
    finish: "Finisci il disegno (clicca sulla mappa per aggiungere punti)",
    draw: "Disegna un'area sulla mappa",
  },
});

/** Operating area: whole city, a municipio, an urban zone or a polygon drawn on the map. */
export function AreaPicker({
  area,
  onChange,
  drawing,
  onDraw,
  label,
  simple = false,
}: {
  area: Area;
  onChange: (a: Area) => void;
  drawing?: boolean;
  onDraw?: () => void;
  label?: string;
  /** Whole city or a municipio only (public service): no urban-zone codes. */
  simple?: boolean;
}) {
  const t = tr(T);
  const value = area.type === "municipio" ? `m:${area.id}` : area.type;
  return (
    <div className="space-y-2">
      <Field label={label ?? t.operatingArea} hint={simple ? undefined : t.selected(areaLabel(area))}>
        <select
          className="input"
          value={value}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "city") onChange({ type: "city" });
            else if (v.startsWith("m:")) onChange({ type: "municipio", id: v.slice(2) });
            else if (v === "zone") onChange({ type: "zone", id: "" });
          }}
        >
          <option value="city">{t.city}</option>
          {MUNICIPI.map((m) => (
            <option key={m} value={`m:${m}`}>
              {t.municipio} {roman(Number(m))}
            </option>
          ))}
          {!simple && <option value="zone">{t.zoneOption}</option>}
          {area.type === "polygon" && <option value="polygon">{t.drawn}</option>}
        </select>
      </Field>
      {area.type === "zone" && (
        <input
          className="input"
          aria-label={t.zoneCode}
          placeholder={t.zonePlaceholder}
          value={area.id}
          onChange={(e) => onChange({ type: "zone", id: e.target.value.trim().toUpperCase() })}
        />
      )}
      {onDraw && (
        <button type="button" className={drawing ? "btn w-full" : "btn-ghost w-full"} onClick={onDraw} aria-pressed={drawing}>
          <PenLine className="h-4 w-4" aria-hidden="true" />
          {drawing ? t.finish : t.draw}
        </button>
      )}
    </div>
  );
}
