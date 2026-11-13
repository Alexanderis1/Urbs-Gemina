import { MUNICIPI, areaLabel, type Area } from "@/lib/area";

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
    <div className="space-y-1">
      <div className="label">Area</div>
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
            Municipio {m}
          </option>
        ))}
        <option value="zone">Urban zone…</option>
        {area.type === "polygon" && <option value="polygon">Drawn area</option>}
      </select>
      {area.type === "zone" && (
        <input
          className="input"
          placeholder="Urban zone id, e.g. 1A"
          value={area.id}
          onChange={(e) => onChange({ type: "zone", id: e.target.value.trim() })}
        />
      )}
      {onDraw && (
        <button className="btn-ghost w-full" onClick={onDraw}>
          {drawing ? "Finish drawing (click map to add points)" : "Draw an area on the map"}
        </button>
      )}
      <div className="text-xs text-stone-500">Selected: {areaLabel(area)}</div>
    </div>
  );
}
