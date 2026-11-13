import { useEffect, useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { CityMap } from "@/map/CityMap";
import { KindBadge } from "@/components/Badge";
import { RunMeta } from "@/components/RunMeta";
import { PROXY, isSampleMode } from "@/api/client";
import { SAMPLE_DISCIPLINES } from "@/api/mockSport";
import { MUNICIPI, roman } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import {
  EDITABLE_FIELDS,
  buildManagerUpdate,
  displayName,
  fieldLabel,
  filterFacilities,
  type Coverage,
  type ManagerUpdate,
  type SportFeature,
  type SportField,
  type WhatIf,
} from "@/lib/sport";
import type { Envelope } from "@/api/types";

type Tab = "map" | "deserts";
const STATUS_COLOR: Record<string, string> = {
  official: "text-real",
  manager_confirmed: "text-real",
  open_data: "text-real",
  web_unverified: "text-estimated",
  simulated: "text-simulated",
  not_known: "text-stone-400",
};

export default function Sport() {
  const { run, tier } = useSession();
  const [tab, setTab] = useState<Tab>("map");
  const [facEnv, setFacEnv] = useState<Envelope<{ features: SportFeature[] }> | null>(null);
  const [discipline, setDiscipline] = useState("");
  const [kind, setKind] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [accessibleOnly, setAccessibleOnly] = useState(false);
  const [selected, setSelected] = useState<SportFeature | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Desert view
  const [desertDisc, setDesertDisc] = useState("football");
  const [desertEnv, setDesertEnv] = useState<Envelope<Coverage> | null>(null);
  const [gym, setGym] = useState<{ lon: number; lat: number } | null>(null);
  const [whatIf, setWhatIf] = useState<Envelope<WhatIf> | null>(null);

  useEffect(() => {
    run<{ features: SportFeature[] }>("sports_facilities", { area: "city", discipline: null }).then(setFacEnv, (e: unknown) =>
      setError(String(e)),
    );
  }, [run]);

  useEffect(() => {
    if (tab !== "deserts") return;
    setWhatIf(null);
    run<Coverage>("sport_deserts", { area: "city", discipline: desertDisc }).then(setDesertEnv, (e: unknown) => setError(String(e)));
  }, [tab, desertDisc, run]);

  const all = facEnv?.result.features ?? [];
  const kinds = useMemo(() => [...new Set(all.map((f) => f.properties.kind))].sort(), [all]);
  const disciplines = useMemo(() => [...new Set(all.flatMap((f) => f.properties.disciplines))].sort(), [all]);
  const shown = useMemo(
    () =>
      tab === "map"
        ? filterFacilities(all, { discipline: discipline || undefined, kind: kind || undefined, municipio: municipio || undefined, accessibleOnly })
        : filterFacilities(all, { discipline: desertDisc }),
    [all, tab, discipline, kind, municipio, accessibleOnly, desertDisc],
  );

  const coverage: Coverage | null = whatIf ? whatIf.result.variant : (desertEnv?.result ?? null);

  const layers = useMemo(() => {
    const pts = shown.filter((f) => f.geometry);
    const out: Layer[] = [];
    if (tab === "deserts" && coverage) {
      out.push(
        new ScatterplotLayer({
          id: "reach",
          data: pts,
          getPosition: (f: SportFeature) => f.geometry!.coordinates,
          getRadius: coverage.reach_m,
          radiusUnits: "meters",
          getFillColor: [21, 128, 61, 40],
          stroked: false,
        }),
        new ScatterplotLayer({
          id: "zones",
          data: coverage.zones.filter((z) => z.centroid),
          getPosition: (z: { centroid?: [number, number] }) => z.centroid!,
          getRadius: 900,
          radiusUnits: "meters",
          getFillColor: (z: { desert: boolean }) => (z.desert ? [190, 30, 30, 70] : [120, 120, 120, 25]),
          getLineColor: (z: { desert: boolean }) => (z.desert ? [190, 30, 30, 220] : [120, 120, 120, 120]),
          stroked: true,
          lineWidthMinPixels: 1,
          updateTriggers: { getFillColor: [coverage], getLineColor: [coverage] },
        }),
      );
      if (gym)
        out.push(
          new ScatterplotLayer({
            id: "gym",
            data: [gym],
            getPosition: (g: { lon: number; lat: number }) => [g.lon, g.lat],
            getRadius: coverage.reach_m,
            radiusUnits: "meters",
            getFillColor: [124, 58, 237, 60],
            getLineColor: [124, 58, 237, 255],
            stroked: true,
            lineWidthMinPixels: 2,
          }),
        );
    }
    out.push(
      new ScatterplotLayer({
        id: "facilities",
        data: pts,
        getPosition: (f: SportFeature) => f.geometry!.coordinates,
        getFillColor: (f: SportFeature) => (f.properties.facility_id === selected?.properties.facility_id ? [139, 30, 45] : [37, 99, 235]),
        radiusMinPixels: 5,
        pickable: true,
        onClick: ({ object }) => {
          if (object) setSelected(object as SportFeature);
          return true;
        },
        updateTriggers: { getFillColor: [selected] },
      }),
    );
    return out;
  }, [shown, tab, coverage, gym, selected]);

  async function runWhatIf() {
    if (!gym) return;
    setWhatIf(
      await run<WhatIf>("sport_deserts", {
        area: "city",
        discipline: desertDisc,
        open_facilities: [{ name: "School gym (what-if)", lon: gym.lon, lat: gym.lat }],
      }),
    );
  }

  return (
    <div className="flex h-full">
      <aside className="w-96 shrink-0 space-y-4 overflow-y-auto border-r border-stone-200 bg-white p-4">
        <div className="flex gap-1">
          {(["map", "deserts"] as const).map((t) => (
            <button key={t} className={t === tab ? "btn" : "btn-ghost"} onClick={() => setTab(t)}>
              {t === "map" ? "Facilities" : "Sport deserts"}
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-red-700">{error}</p>}

        {tab === "map" && (
          <div className="space-y-2">
            <Select label="Discipline" value={discipline} onChange={setDiscipline} options={disciplines} />
            <Select label="Kind" value={kind} onChange={setKind} options={kinds} />
            <Select label="Municipio" value={municipio} onChange={setMunicipio} options={MUNICIPI} show={(m) => `Municipio ${roman(Number(m))}`} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={accessibleOnly} onChange={(e) => setAccessibleOnly(e.target.checked)} />
              Accessible (stated by a source)
            </label>
            <p className="text-xs text-stone-500">{shown.length} facilities shown. Click one on the map.</p>
            {facEnv && <RunMeta env={facEnv} compact />}
          </div>
        )}

        {tab === "deserts" && (
          <div className="space-y-3">
            <Select label="Discipline" value={desertDisc} onChange={setDesertDisc} options={disciplines.length ? disciplines : SAMPLE_DISCIPLINES} noAll />
            {coverage && (
              <div className="card space-y-1 text-sm">
                <div>
                  Residents without a {coverage.discipline} facility within {Math.round(coverage.reach_m)} m:{" "}
                  <b>{coverage.residents_uncovered.toLocaleString()}</b> of {coverage.residents_total.toLocaleString()}
                </div>
                <div>Children: {coverage.children_uncovered.toLocaleString()} of {coverage.children_total.toLocaleString()}</div>
                <div className="text-xs text-stone-500">Reach is a straight-line estimate of a walk.</div>
                {coverage.desert_zones.length > 0 && <div className="text-red-700">Desert zones: {coverage.desert_zones.join(", ")}</div>}
              </div>
            )}
            <div className="card space-y-2 text-sm">
              <div className="label">What if: open a school gym</div>
              <p className="text-xs text-stone-500">{gym ? `Gym at ${gym.lat.toFixed(4)}, ${gym.lon.toFixed(4)}` : "Click the map to place the gym."}</p>
              <button className="btn w-full" disabled={!gym} onClick={() => void runWhatIf()}>
                Compare with and without
              </button>
              {whatIf && (
                <div className="space-y-1">
                  <KindBadge kind="simulated" label="what-if" />
                  <div>
                    Newly covered residents: <b>{whatIf.result.delta.residents_newly_covered.toLocaleString()}</b>, children:{" "}
                    <b>{whatIf.result.delta.children_newly_covered.toLocaleString()}</b>
                  </div>
                  <div className="text-xs">
                    Desert zones: {whatIf.result.baseline.desert_zones.length} before, {whatIf.result.variant.desert_zones.length} after
                  </div>
                </div>
              )}
            </div>
            {(whatIf ?? desertEnv) && <RunMeta env={(whatIf ?? desertEnv)!} />}
          </div>
        )}

        {selected && <FacilityPage f={selected} canManage={tier === "office"} onClose={() => setSelected(null)} />}
      </aside>
      <div className="flex-1">
        <CityMap layers={layers} initialZoom={11.5} pitch={30} onClick={tab === "deserts" ? (p) => setGym({ lon: p.lon, lat: p.lat }) : undefined} />
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  show = (s) => s.replace(/_/g, " "),
  noAll = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  show?: (s: string) => string;
  noAll?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="label">{label}</div>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {!noAll && <option value="">All</option>}
        {options.map((o) => (
          <option key={o} value={o}>
            {show(o)}
          </option>
        ))}
      </select>
    </div>
  );
}

function FieldRow({ name, f }: { name: string; f: SportField }) {
  const value = f.value == null ? "—" : f.value === true ? "yes" : f.value === false ? "no" : typeof f.value === "object" ? JSON.stringify(f.value) : String(f.value);
  return (
    <li className="py-1">
      <div className="flex justify-between gap-2">
        <span className="font-medium">{name.replace(/_/g, " ")}</span>
        <span>{value}</span>
      </div>
      <div className={`text-xs ${STATUS_COLOR[f.status] ?? ""}`}>{fieldLabel(f)}</div>
      {f.sources.map((s, i) => (
        <div key={i} className="text-xs text-stone-500">
          {s.url ? (
            <a className="underline" href={s.url} target="_blank" rel="noreferrer">
              {s.source}
            </a>
          ) : (
            s.source
          )}
          {s.retrieved_at ? ` · ${s.retrieved_at}` : ""}
          {s.confidence != null ? ` · confidence ${Math.round(s.confidence * 100)}%` : ""}
          {s.quote ? ` · “${s.quote}”` : ""}
        </div>
      ))}
    </li>
  );
}

const MANAGER_URL = PROXY ? `${PROXY}/sports/manager_update` : "";

function FacilityPage({ f, canManage, onClose }: { f: SportFeature; canManage: boolean; onClose: () => void }) {
  const p = f.properties;
  const [field, setField] = useState<string>("hours");
  const [value, setValue] = useState("");
  const [account, setAccount] = useState("org:");
  const [saved, setSaved] = useState<ManagerUpdate[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  async function confirm() {
    try {
      const v = field === "disciplines" ? value.split(",").map((s) => s.trim()).filter(Boolean) : value;
      const u = buildManagerUpdate(p.facility_id, field, v, account, new Date().toISOString());
      if (MANAGER_URL && !isSampleMode) {
        const res = await fetch(MANAGER_URL, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(u) });
        if (!res.ok) {
          // The sports module rejects bad fields or disciplines with a validation message.
          const body = (await res.json().catch(() => ({}))) as { detail?: unknown; reason?: unknown };
          throw new Error(String(body.detail ?? body.reason ?? `HTTP ${res.status}`));
        }
        setMsg("Sent. The value will show as confirmed by manager after the next refresh.");
      } else setMsg("Sample mode: kept in this browser only.");
      setSaved((s) => [u, ...s]);
      setValue("");
    } catch (e) {
      setMsg(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <div className="card space-y-2 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold">{displayName(f)}</div>
          <div className="text-xs text-stone-500">
            {p.kind.replace(/_/g, " ")}
            {p.municipio ? ` · Municipio ${roman(Number(p.municipio))}` : ""}
          </div>
        </div>
        <button className="text-stone-400" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      {p.synthetic && <KindBadge kind="simulated" />}
      <div className="label">Disciplines</div>
      <ul className="divide-y divide-stone-100">
        {Object.entries(p.discipline_details).map(([d, v]) => (
          <FieldRow key={d} name={d} f={v} />
        ))}
      </ul>
      <div className="label">Details</div>
      <ul className="divide-y divide-stone-100">
        {Object.entries(p.fields).map(([k, v]) => (
          <FieldRow key={k} name={k} f={v} />
        ))}
      </ul>
      {canManage && (
        <div className="space-y-2 border-t border-stone-200 pt-2">
          <div className="label">Manager: confirm or correct</div>
          <select className="input" value={field} onChange={(e) => setField(e.target.value)}>
            {EDITABLE_FIELDS.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          <input className="input" placeholder={field === "disciplines" ? "football, tennis" : "New value"} value={value} onChange={(e) => setValue(e.target.value)} />
          <input className="input" placeholder="org:your-club" value={account} onChange={(e) => setAccount(e.target.value.toLowerCase())} />
          <p className="text-xs text-stone-500">Organisation account only. Use the club's public contact, never a person's.</p>
          <button className="btn w-full" onClick={() => void confirm()} disabled={!value}>
            Confirm
          </button>
          {msg && <p className="text-xs">{msg}</p>}
          {saved.map((u) => (
            <div key={u.confirmed_at} className="text-xs text-stone-500">
              {u.field} → {JSON.stringify(u.value)} by {u.account_ref}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
