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
import { errorText } from "@/lib/errors";
import { locale, tr } from "@/lib/i18n";
import { T } from "@/pages/Sport.text";

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
  const t = tr(T);
  const num = (n: number) => n.toLocaleString(locale());
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
      setError(errorText(e)),
    );
  }, [run]);

  useEffect(() => {
    if (tab !== "deserts") return;
    setWhatIf(null);
    run<Coverage>("sport_coverage", { area: "city", discipline: desertDisc }).then(setDesertEnv, (e: unknown) => setError(errorText(e)));
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
        open_school_gyms: [{ name: t.gymName, lon: gym.lon, lat: gym.lat }],
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
        <Panel title="Sport" icon={Trophy} subtitle={t.subtitle} width="w-[24rem]">
          <Segmented
            label={t.view}
            value={tab}
            onChange={(t) => {
              // The facility sheet belongs to the Facilities tab: close it when leaving.
              setTab(t);
              setSelected(null);
            }}
            options={[
              { id: "map", label: t.facilities },
              { id: "deserts", label: t.deserts },
            ]}
          />
          {error && <Callout tone="error">{error}</Callout>}

          {tab === "map" && (
            <>
              <Section title={t.filters}>
                <div className="grid grid-cols-2 gap-2">
                  <Select label={t.discipline} value={discipline} onChange={setDiscipline} options={disciplines} />
                  <Select label={t.kind} value={kind} onChange={setKind} options={kinds} />
                  <Select label={t.type} value={ftype} onChange={setFtype} options={FACILITY_TYPES} show={(t) => typeLabel(t as FacilityType)} />
                  <Select label="Municipio" value={municipio} onChange={setMunicipio} options={MUNICIPI} show={(m) => `Municipio ${roman(Number(m))}`} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="check" checked={accessibleOnly} onChange={(e) => setAccessibleOnly(e.target.checked)} />
                  {t.accessibleOnly}
                </label>
              </Section>
              <Stat
                label={t.shown}
                value={num(shown.length)}
                note={clustered ? t.clusteredNote : t.clickOne}
              />
              <p className="hint">{t.greyHint}</p>
              {facEnv && (
                <Section title={t.evidence} collapsible defaultOpen={false}>
                  <RunMeta env={facEnv} compact />
                </Section>
              )}
            </>
          )}

          {tab === "deserts" && (
            <>
              <Select label={t.discipline} value={desertDisc} onChange={setDesertDisc} options={disciplines.length ? disciplines : SAMPLE_DISCIPLINES} noAll />
              {coverage && (
                <Section title={t.coverage}>
                  <div className="grid grid-cols-1 gap-2">
                    <Stat
                      label={t.residentsWithout(reach)}
                      value={num(coverage.residents_uncovered)}
                      note={t.of(num(coverage.residents_total))}
                      tone="danger"
                    />
                    <Stat
                      label={t.childrenWithout(reach)}
                      value={num(coverage.children_uncovered)}
                      note={t.of(num(coverage.children_total))}
                      tone="danger"
                    />
                  </div>
                  <p className="hint">{t.reachHint}</p>
                  {coverage.desert_zones.length > 0 && (
                    <div>
                      <div className="label mb-1">{t.desertZones}</div>
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
                  <h2 className="label">{t.whatIfTitle}</h2>
                  <KindBadge kind="simulated" text={t.whatIfBadge} />
                </div>
                <p className="hint">{gym ? t.gymAt(gym.lat.toFixed(4), gym.lon.toFixed(4)) : t.placeGym}</p>
                <button type="button" className="btn w-full" disabled={!gym} onClick={() => void runWhatIf()}>
                  {t.compare}
                </button>
                {whatIf && (
                  <div className="animate-rise-in space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <Stat label={t.newResidents} value={num(whatIf.result.delta.residents_newly_covered)} tone="whatif" />
                      <Stat label={t.newChildren} value={num(whatIf.result.delta.children_newly_covered)} tone="whatif" />
                    </div>
                    <p className="hint">
                      {t.desertBeforeAfter(whatIf.result.baseline.desert_zones.length, whatIf.result.variant.desert_zones.length)}
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
              <button type="button" className="btn-quiet btn-sm" onClick={() => setSelected(null)} aria-label={t.closeFacility}>
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            }
          >
            <FacilityPage key={selected.properties.facility_id} f={selected} canManage={tier === "office"} />
          </Panel>
        )
      }
    >
      <CityMap layers={layers} pitch={30} onZoom={setZoom} onClick={tab === "deserts" ? (p) => setGym({ lon: p.lon, lat: p.lat }) : undefined} />
      <MapFloat position="bottom-left">
        <div className="label mb-1">{t.mapKey}</div>
        <ul className="space-y-1 text-xs">
          {tab === "map" ? (
            <>
              <LegendRow swatch={sw(palette.point)} text={t.legUsable} />
              <LegendRow
                swatch={<span aria-hidden="true" className="inline-block h-3 w-3 shrink-0 rounded-full border-2 border-white bg-link ring-2 ring-link" />}
                text={t.legSelected}
              />
              <LegendRow swatch={sw(palette.inactive)} text={t.legClosed} />
              <LegendRow swatch={sw(palette.point, false)} text={t.legHex} />
            </>
          ) : (
            <>
              <LegendRow swatch={sw(palette.good, true, true)} text={t.legReach} />
              <LegendRow swatch={sw(palette.bad, true, true)} text={t.legDesert} />
              <LegendRow swatch={sw(palette.inactive, true, true)} text={t.legOther} />
              <LegendRow swatch={sw(palette.whatIf, true, true)} text={t.gymName} />
            </>
          )}
        </ul>
      </MapFloat>
    </Workspace>
  );
}

function facilitySubtitle(f: SportFeature): string {
  const p = f.properties;
  const t = tr(T);
  return `${p.kind.replace(/_/g, " ")} · ${typeLabel(p.type)} · ${t.accessible}: ${
    p.accessible === true ? t.yes : p.accessible === false ? t.no : t.notKnown
  } · ${accessLabel(p.access)}${p.closed ? ` · ${t.closed}` : ""}${p.municipio ? ` · Municipio ${roman(Number(p.municipio))}` : ""}`;
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
  const t = tr(T);
  return (
    <Field label={label}>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {!noAll && <option value="">{t.all}</option>}
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
  const t = tr(T);
  const value = f.value == null ? "—" : f.value === true ? t.yes : f.value === false ? t.no : typeof f.value === "object" ? JSON.stringify(f.value) : String(f.value);
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
          {s.confidence != null ? ` · ${t.confidence} ${Math.round(s.confidence * 100)}%` : ""}
          {s.quote ? ` · “${s.quote}”` : ""}
        </div>
      ))}
    </li>
  );
}

function FacilityPage({ f, canManage }: { f: SportFeature; canManage: boolean }) {
  const p = f.properties;
  const t = tr(T);
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
        setMsg({ ok: true, text: t.sent });
      } else setMsg({ ok: true, text: t.sampleKept });
      setSaved((s) => [u, ...s]);
      setValue("");
    } catch (e) {
      setMsg({ ok: false, text: `${t.notSaved}: ${errorText(e)}` });
    }
  }

  return (
    <>
      {p.synthetic && (
        <div>
          <KindBadge kind="simulated" />
        </div>
      )}
      <Section title={t.disciplines}>
        <ul className="divide-y divide-line">
          {Object.entries(p.discipline_details).map(([d, v]) => (
            <FieldRow key={d} name={d} f={v} />
          ))}
        </ul>
      </Section>
      <Section title={t.details}>
        <ul className="divide-y divide-line">
          {Object.entries(p.fields).map(([k, v]) => (
            <FieldRow key={k} name={k} f={v} />
          ))}
        </ul>
      </Section>
      {canManage && (
        <Section title={t.managerTitle}>
          <Field label={t.field}>
            <select className="input" value={field} onChange={(e) => setField(e.target.value)}>
              {EDITABLE_FIELDS.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label={t.newValue}>
            <input className="input" placeholder={field === "disciplines" ? "football, tennis" : t.newValue} value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
          <Field label={t.orgAccount} hint={t.orgHint}>
            <input className="input" placeholder="org:your-club" value={account} onChange={(e) => setAccount(e.target.value.toLowerCase())} />
          </Field>
          <button type="button" className="btn w-full" onClick={() => void confirm()} disabled={!value}>
            {t.confirm}
          </button>
          {msg && <Callout tone={msg.ok ? "info" : "error"}>{msg.text}</Callout>}
          {saved.map((u) => (
            <div key={u.confirmed_at} className="hint">
              {u.field} → {JSON.stringify(u.value)} {t.by} {u.account_ref}
            </div>
          ))}
        </Section>
      )}
    </>
  );
}
