import { useEffect, useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import type { Layer } from "@deck.gl/core";
import { Trophy, X } from "lucide-react";
import { CityMap } from "@/map/CityMap";
import { Callout, Field, MapFloat, Panel, Section, Segmented, Stat, Workspace } from "@/components/ui";
import { useTheme } from "@/lib/useTheme";
import { KindBadge } from "@/components/Badge";
import { RunMeta } from "@/components/RunMeta";
import { isSampleMode, proxyFetch } from "@/api/client";
import { SAMPLE_DISCIPLINES } from "@/api/mockSport";
import { MUNICIPI, roman } from "@/lib/area";
import { useSession } from "@/lib/runlog";
import {
  EDITABLE_FIELDS,
  FACILITY_TYPES,
  typeLabel,
  accessLabel,
  isInactive,
  clusterH3,
  shouldCluster,
  type FacilityCell,
  type FacilityType,
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
  not_known: "text-muted",
};

export default function Sport() {
  const { run, tier } = useSession();
  const { palette } = useTheme();
  const [tab, setTab] = useState<Tab>("map");
  const [facEnv, setFacEnv] = useState<Envelope<{ features: SportFeature[] }> | null>(null);
  const [discipline, setDiscipline] = useState("");
  const [kind, setKind] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [accessibleOnly, setAccessibleOnly] = useState(false);
  const [zoom, setZoom] = useState(11.5);
  const [ftype, setFtype] = useState("");
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
    run<Coverage>("sport_coverage", { area: "city", discipline: desertDisc }).then(setDesertEnv, (e: unknown) => setError(String(e)));
  }, [tab, desertDisc, run]);

  const all = facEnv?.result.features ?? [];
  const kinds = useMemo(() => [...new Set(all.map((f) => f.properties.kind))].sort(), [all]);
  const disciplines = useMemo(() => [...new Set(all.flatMap((f) => f.properties.disciplines))].sort(), [all]);
  const shown = useMemo(
    () =>
      tab === "map"
        ? filterFacilities(all, {
            discipline: discipline || undefined,
            kind: kind || undefined,
            municipio: municipio || undefined,
            type: (ftype || undefined) as FacilityType | undefined,
            accessibleOnly,
          })
        : filterFacilities(all, { discipline: desertDisc }),
    [all, tab, discipline, kind, municipio, ftype, accessibleOnly, desertDisc],
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
          getFillColor: [...palette.good, 45],
          stroked: false,
        }),
        new ScatterplotLayer({
          id: "zones",
          data: coverage.zones.filter((z) => z.centroid),
          getPosition: (z: { centroid?: [number, number] }) => z.centroid!,
          getRadius: 900,
          radiusUnits: "meters",
          getFillColor: (z: { desert: boolean }) => (z.desert ? [...palette.bad, 80] : [...palette.inactive, 30]),
          getLineColor: (z: { desert: boolean }) => (z.desert ? [...palette.bad, 230] : [...palette.inactive, 130]),
          stroked: true,
          lineWidthMinPixels: 1,
          updateTriggers: { getFillColor: [coverage, palette], getLineColor: [coverage, palette] },
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
            getFillColor: [...palette.whatIf, 60],
            getLineColor: [...palette.whatIf, 255],
            stroked: true,
            lineWidthMinPixels: 2,
          }),
        );
    }
    if (shouldCluster(pts.length, zoom)) {
      // Zoomed out over thousands of facilities: one hexagon per ~0.7 km², coloured by how many are usable.
      const cells = clusterH3(pts, zoom < 11 ? 7 : 8);
      const max = Math.max(1, ...cells.map((c) => c.count));
      out.push(
        new H3HexagonLayer<FacilityCell>({
          id: "facility-cells",
          data: cells,
          getHexagon: (c) => c.h3,
          extruded: false,
          getFillColor: (c) =>
            c.active === 0 ? [...palette.inactive, 120] : [...palette.point, Math.round(60 + 180 * (c.count / max))],
          getLineColor: [255, 255, 255, 160],
          lineWidthMinPixels: 0.5,
          pickable: false,
          updateTriggers: { getFillColor: [palette, max] },
        }),
      );
    } else {
      out.push(
        new ScatterplotLayer({
          id: "facilities",
          data: pts,
          getPosition: (f: SportFeature) => f.geometry!.coordinates,
          getFillColor: (f: SportFeature) =>
            f.properties.facility_id === selected?.properties.facility_id
              ? [...palette.accent, 255]
              : isInactive(f)
                ? [...palette.inactive, 170]
                : [...palette.point, 255],
          radiusMinPixels: pts.length > 3000 ? 3 : 5,
          pickable: true,
          onClick: ({ object }) => {
            if (object) setSelected(object as SportFeature);
            return true;
          },
          updateTriggers: { getFillColor: [selected, palette] },
        }),
      );
      // Selected facility: larger with a white outline, so it stands out even when accent equals point.
      if (selected?.geometry)
        out.push(
          new ScatterplotLayer({
            id: "facility-selected",
            data: [selected],
            getPosition: (f: SportFeature) => f.geometry!.coordinates,
            getFillColor: [...palette.accent, 255],
            getLineColor: [255, 255, 255, 255],
            stroked: true,
            lineWidthMinPixels: 2,
            radiusMinPixels: 9,
            updateTriggers: { getFillColor: [palette] },
          }),
        );
    }
    return out;
  }, [shown, tab, coverage, gym, selected, zoom, palette]);

  async function runWhatIf() {
    if (!gym) return;
    setWhatIf(
      await run<WhatIf>("sport_coverage", {
        area: "city",
        discipline: desertDisc,
        open_school_gyms: [{ name: "School gym (what-if)", lon: gym.lon, lat: gym.lat }],
      }),
    );
  }

  const clustered = shouldCluster(shown.length, zoom);
  const done = whatIf ?? desertEnv;
  const reach = coverage ? Math.round(coverage.reach_m) : 0;
  const sw = (c: number[], round = true, ring = false) => (
    <span
      aria-hidden="true"
      className={`inline-block h-3 w-3 shrink-0 ${round ? "rounded-full" : "rounded-sm"} ${ring ? "border-2" : "border border-white/70"}`}
      style={ring ? { borderColor: `rgb(${c.join(",")})`, background: `rgba(${c.join(",")},0.18)` } : { background: `rgb(${c.join(",")})` }}
    />
  );
  const LegendRow = ({ swatch, text }: { swatch: React.ReactNode; text: string }) => (
    <li className="flex items-center gap-2">
      {swatch}
      <span>{text}</span>
    </li>
  );

  return (
    <Workspace
      panel={
        <Panel title="Sport" icon={Trophy} subtitle="Facilities and areas without them" width="w-[24rem]">
          <Segmented
            label="View"
            value={tab}
            onChange={(t) => {
              // The facility sheet belongs to the Facilities tab: close it when leaving.
              setTab(t);
              setSelected(null);
            }}
            options={[
              { id: "map", label: "Facilities" },
              { id: "deserts", label: "Sport deserts" },
            ]}
          />
          {error && <Callout tone="error">{error}</Callout>}

          {tab === "map" && (
            <>
              <Section title="Filters">
                <div className="grid grid-cols-2 gap-2">
                  <Select label="Discipline" value={discipline} onChange={setDiscipline} options={disciplines} />
                  <Select label="Kind" value={kind} onChange={setKind} options={kinds} />
                  <Select label="Type" value={ftype} onChange={setFtype} options={FACILITY_TYPES} show={(t) => typeLabel(t as FacilityType)} />
                  <Select label="Municipio" value={municipio} onChange={setMunicipio} options={MUNICIPI} show={(m) => `Municipio ${roman(Number(m))}`} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="check" checked={accessibleOnly} onChange={(e) => setAccessibleOnly(e.target.checked)} />
                  Accessible (stated by a source)
                </label>
              </Section>
              <Stat
                label="Facilities shown"
                value={shown.length.toLocaleString()}
                note={clustered ? "Grouped in hexagons when zoomed out: zoom in to click one." : "Click one on the map."}
              />
              <p className="hint">Grey = closed, private or no access. These do not count in coverage.</p>
              {facEnv && (
                <Section title="Evidence" collapsible defaultOpen={false}>
                  <RunMeta env={facEnv} compact />
                </Section>
              )}
            </>
          )}

          {tab === "deserts" && (
            <>
              <Select label="Discipline" value={desertDisc} onChange={setDesertDisc} options={disciplines.length ? disciplines : SAMPLE_DISCIPLINES} noAll />
              {coverage && (
                <Section title="Coverage">
                  <div className="grid grid-cols-1 gap-2">
                    <Stat
                      label={`Residents without one within ${reach} m`}
                      value={coverage.residents_uncovered.toLocaleString()}
                      note={`of ${coverage.residents_total.toLocaleString()}`}
                      tone="danger"
                    />
                    <Stat
                      label={`Children without one within ${reach} m`}
                      value={coverage.children_uncovered.toLocaleString()}
                      note={`of ${coverage.children_total.toLocaleString()}`}
                      tone="danger"
                    />
                  </div>
                  <p className="hint">Reach is a straight-line estimate of a walk.</p>
                  {coverage.desert_zones.length > 0 && (
                    <div>
                      <div className="label mb-1">Desert zones</div>
                      <ul className="flex flex-wrap gap-1">
                        {coverage.desert_zones.map((z) => (
                          <li key={z} className="rounded-sm border border-danger/40 bg-danger/10 px-1.5 text-xs">
                            {z}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Section>
              )}
              <div className="card space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="label">What if: open a school gym</h2>
                  <KindBadge kind="simulated" text="what-if" />
                </div>
                <p className="hint">{gym ? `Gym at ${gym.lat.toFixed(4)}, ${gym.lon.toFixed(4)}` : "Click the map to place the gym."}</p>
                <button type="button" className="btn w-full" disabled={!gym} onClick={() => void runWhatIf()}>
                  Compare with and without
                </button>
                {whatIf && (
                  <div className="animate-rise-in space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <Stat label="Newly covered residents" value={whatIf.result.delta.residents_newly_covered.toLocaleString()} tone="whatif" />
                      <Stat label="Newly covered children" value={whatIf.result.delta.children_newly_covered.toLocaleString()} tone="whatif" />
                    </div>
                    <p className="hint">
                      Desert zones: {whatIf.result.baseline.desert_zones.length} before, {whatIf.result.variant.desert_zones.length} after
                    </p>
                  </div>
                )}
              </div>
              {done && <RunMeta env={done} />}
            </>
          )}
        </Panel>
      }
      right={
        selected && (
          <Panel
            side="right"
            width="w-[24rem]"
            title={displayName(selected)}
            subtitle={facilitySubtitle(selected)}
            actions={
              <button type="button" className="btn-quiet btn-sm" onClick={() => setSelected(null)} aria-label="Close facility">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            }
          >
            <FacilityPage key={selected.properties.facility_id} f={selected} canManage={tier === "office"} />
          </Panel>
        )
      }
    >
      <CityMap layers={layers} initialZoom={11.5} pitch={30} onZoom={setZoom} onClick={tab === "deserts" ? (p) => setGym({ lon: p.lon, lat: p.lat }) : undefined} />
      <MapFloat position="bottom-left">
        <div className="label mb-1">Map key</div>
        <ul className="space-y-1 text-xs">
          {tab === "map" ? (
            <>
              <LegendRow swatch={sw(palette.point)} text="Usable facility" />
              <LegendRow
                swatch={<span aria-hidden="true" className="inline-block h-3 w-3 shrink-0 rounded-full border-2 border-white bg-link ring-2 ring-link" />}
                text="Selected facility (larger, white outline)"
              />
              <LegendRow swatch={sw(palette.inactive)} text="Closed, private or no access" />
              <LegendRow swatch={sw(palette.point, false)} text="Hexagon: facilities grouped (darker = more)" />
            </>
          ) : (
            <>
              <LegendRow swatch={sw(palette.good, true, true)} text="Within walking reach of a facility" />
              <LegendRow swatch={sw(palette.bad, true, true)} text="Sport desert zone" />
              <LegendRow swatch={sw(palette.inactive, true, true)} text="Other zone" />
              <LegendRow swatch={sw(palette.whatIf, true, true)} text="School gym (what-if)" />
            </>
          )}
        </ul>
      </MapFloat>
    </Workspace>
  );
}

function facilitySubtitle(f: SportFeature): string {
  const p = f.properties;
  return `${p.kind.replace(/_/g, " ")} · ${typeLabel(p.type)} · accessible: ${
    p.accessible === true ? "yes" : p.accessible === false ? "no" : "not known"
  } · ${accessLabel(p.access)}${p.closed ? " · closed" : ""}${p.municipio ? ` · Municipio ${roman(Number(p.municipio))}` : ""}`;
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
    <Field label={label}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {!noAll && <option value="">All</option>}
        {options.map((o) => (
          <option key={o} value={o}>
            {show(o)}
          </option>
        ))}
      </select>
    </Field>
  );
}

function FieldRow({ name, f }: { name: string; f: SportField }) {
  const value = f.value == null ? "—" : f.value === true ? "yes" : f.value === false ? "no" : typeof f.value === "object" ? JSON.stringify(f.value) : String(f.value);
  return (
    <li className="space-y-0.5 py-2 text-sm">
      <div className="flex justify-between gap-2">
        <span className="font-semibold">{name.replace(/_/g, " ")}</span>
        <span className="min-w-0 break-words text-right">{value}</span>
      </div>
      <div className={`text-xs ${STATUS_COLOR[f.status] ?? "text-muted"}`}>{fieldLabel(f)}</div>
      {f.sources.map((s, i) => (
        <div key={i} className="hint break-words">
          {s.url ? (
            <a className="text-link underline" href={s.url} target="_blank" rel="noreferrer">
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

function FacilityPage({ f, canManage }: { f: SportFeature; canManage: boolean }) {
  const p = f.properties;
  const [field, setField] = useState<string>("hours");
  const [value, setValue] = useState("");
  const [account, setAccount] = useState("org:");
  const [saved, setSaved] = useState<ManagerUpdate[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function confirm() {
    try {
      const v = field === "disciplines" ? value.split(",").map((s) => s.trim()).filter(Boolean) : value;
      const u = buildManagerUpdate(p.facility_id, field, v, account, new Date().toISOString());
      if (!isSampleMode) {
        const res = await proxyFetch("/sports/manager_update", u);
        if (!res.ok) {
          // The sports module rejects bad fields or disciplines with a validation message.
          const body = (await res.json().catch(() => ({}))) as { detail?: unknown; reason?: unknown };
          throw new Error(String(body.detail ?? body.reason ?? `HTTP ${res.status}`));
        }
        setMsg({ ok: true, text: "Sent. The value will show as confirmed by manager after the next refresh." });
      } else setMsg({ ok: true, text: "Sample mode: kept in this browser only." });
      setSaved((s) => [u, ...s]);
      setValue("");
    } catch (e) {
      setMsg({ ok: false, text: `Not saved: ${e instanceof Error ? e.message : String(e)}` });
    }
  }

  return (
    <>
      {p.synthetic && (
        <div>
          <KindBadge kind="simulated" />
        </div>
      )}
      <Section title="Disciplines">
        <ul className="divide-y divide-line">
          {Object.entries(p.discipline_details).map(([d, v]) => (
            <FieldRow key={d} name={d} f={v} />
          ))}
        </ul>
      </Section>
      <Section title="Details">
        <ul className="divide-y divide-line">
          {Object.entries(p.fields).map(([k, v]) => (
            <FieldRow key={k} name={k} f={v} />
          ))}
        </ul>
      </Section>
      {canManage && (
        <Section title="Manager: confirm or correct">
          <Field label="Field">
            <select className="input" value={field} onChange={(e) => setField(e.target.value)}>
              {EDITABLE_FIELDS.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="New value">
            <input className="input" placeholder={field === "disciplines" ? "football, tennis" : "New value"} value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
          <Field label="Organisation account" hint="Organisation account only. Use the club's public contact, never a person's.">
            <input className="input" placeholder="org:your-club" value={account} onChange={(e) => setAccount(e.target.value.toLowerCase())} />
          </Field>
          <button type="button" className="btn w-full" onClick={() => void confirm()} disabled={!value}>
            Confirm
          </button>
          {msg && <Callout tone={msg.ok ? "info" : "error"}>{msg.text}</Callout>}
          {saved.map((u) => (
            <div key={u.confirmed_at} className="hint">
              {u.field} → {JSON.stringify(u.value)} by {u.account_ref}
            </div>
          ))}
        </Section>
      )}
    </>
  );
}
