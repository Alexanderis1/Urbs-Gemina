import { PenLine } from "lucide-react";
import { MUNICIPI, areaLabel, roman, type Area } from "@/lib/area";
import { Field } from "./ui";

/** Operating area: whole city, a municipio, an urban zone or a polygon drawn on the map. */
export function AreaPicker({
  area,
  onChange,
  drawing,
  onDraw,
}: {
  area: Area;
  onChange: (a: Area) => void;
  drawing?: boolean;
  onDraw?: () => void;
}) {
  const value = area.type === "municipio" ? `m:${area.id}` : area.type;
  return (
    <div className="space-y-2">
      <Field label="Operating area" hint={`Selected: ${areaLabel(area)}`}>
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
          <option value="city">Whole city</option>
          {MUNICIPI.map((m) => (
            <option key={m} value={`m:${m}`}>
              Municipio {roman(Number(m))}
            </option>
          ))}
          <option value="zone">Urban zone…</option>
          {area.type === "polygon" && <option value="polygon">Drawn area</option>}
        </select>
      </Field>
      {area.type === "zone" && (
        <input
          className="input"
          aria-label="Urban zone code"
          placeholder="Urban zone code, e.g. 1A"
          value={area.id}
          onChange={(e) => onChange({ type: "zone", id: e.target.value.trim().toUpperCase() })}
        />
      )}
      {onDraw && (
        <button type="button" className={drawing ? "btn w-full" : "btn-ghost w-full"} onClick={onDraw} aria-pressed={drawing}>
          <PenLine className="h-4 w-4" aria-hidden="true" />
          {drawing ? "Finish drawing (click the map to add points)" : "Draw an area on the map"}
        </button>
      )}
    </div>
  );
}
