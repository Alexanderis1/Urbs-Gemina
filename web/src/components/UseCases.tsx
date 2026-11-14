import { useEffect, useState } from "react";
import {
  Bus,
  CalendarDays,
  ChevronRight,
  Factory,
  Home,
  LifeBuoy,
  ListChecks,
  Play,
  RadioTower,
  School,
  Siren,
  Sunrise,
  ThermometerSun,
  Trophy,
  Wind,
  type LucideIcon,
} from "lucide-react";
import { isSampleMode, proxyRead } from "@/api/client";
import type { Language } from "@/api/twin";
// Sample mode only: a copy of the server's catalogue so the screen can be shown without the API.
import SAMPLE from "@/api/sampleUseCases.json";
import { AreaPicker } from "./AreaPicker";
import { Field, Panel, Section, Spinner } from "./ui";
import type { Area } from "@/lib/area";
import { forTier, paramFields, parseUseCases, useCaseReady, type UseCase } from "@/lib/useCases";
import { useSession } from "@/lib/runlog";

export const USE_CASE_ICON: Record<string, LucideIcon> = {
  municipio_briefing: Sunrise,
  civil_protection_alert: Siren,
  heat_plan_elderly: ThermometerSun,
  site_risk_check: School,
  event_planning: CalendarDays,
  antenna_permit: RadioTower,
  sport_deserts: Trophy,
  citizen_area_info: Home,
  citizen_emergency_info: LifeBuoy,
  industrial_accident: Factory,
  air_quality_episode: Wind,
  strike_day_mobility: Bus,
};

/** The use cases this session may run. Empty while loading, when the service has none, or when it cannot be reached. */
export function useUseCases(): UseCase[] {
  const { tier } = useSession();
  const [list, setList] = useState<UseCase[]>([]);
  useEffect(() => {
    let live = true;
    if (isSampleMode) return setList(forTier(parseUseCases(SAMPLE), tier));
    proxyRead("/use_cases")
      .then((r) => (r.ok ? r.json() : []))
      .then((raw) => live && setList(parseUseCases(raw)))
      .catch(() => undefined); // No catalogue: the panel simply does not appear.
    return () => {
      live = false;
    };
  }, [tier]);
  return list;
}

export interface UseCaseRun {
  useCase: UseCase;
  place: string;
  area: Area;
  values: Record<string, string>;
}

/** Left panel of the Ask screen: pick a ready-made task, give it a place or an area, run it. */
export function UseCasePanel({
  title,
  subtitle,
  useCases,
  language,
  busy,
  onRun,
}: {
  title: string;
  subtitle: string;
  useCases: UseCase[];
  language: Language;
  busy: boolean;
  onRun: (run: UseCaseRun) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [place, setPlace] = useState("");
  const [area, setArea] = useState<Area>({ type: "municipio", id: "1" });
  const [values, setValues] = useState<Record<string, string>>({});

  return (
    <Panel title={title} icon={ListChecks} subtitle={subtitle} width="w-[23rem]">
      <ul className="space-y-1.5">
        {useCases.map((uc) => {
          const Icon = USE_CASE_ICON[uc.id] ?? ListChecks;
          const open = uc.id === openId;
          const fields = paramFields(uc);
          const needsPlace = uc.needs.includes("place");
          return (
            <li key={uc.id} className={`rounded border transition-colors duration-150 ${open ? "border-link bg-primary-soft/50" : "border-line hover:border-line-strong"}`}>
              <button
                type="button"
                className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left"
                aria-expanded={open}
                onClick={() => {
                  setOpenId(open ? null : uc.id);
                  setValues({});
                }}
              >
                <Icon className={`mt-0.5 h-[1.125rem] w-[1.125rem] shrink-0 ${open ? "text-link" : "text-muted"}`} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className={`block text-sm font-semibold leading-snug ${open ? "text-link" : ""}`}>{uc.title[language]}</span>
                  <span className="hint mt-0.5 block leading-snug">{uc.summary[language]}</span>
                </span>
                <ChevronRight className={`mt-1 h-4 w-4 shrink-0 text-muted transition-transform duration-200 ${open ? "rotate-90" : ""}`} aria-hidden="true" />
              </button>
              {open && (
                <form
                  className="animate-fade-in space-y-3 border-t border-line px-3 py-3"
                  onSubmit={(e) => {
                    e.preventDefault();
                    onRun({ useCase: uc, place, area, values });
                  }}
                >
                  {needsPlace ? (
                    <Field label="Address or place" hint="A street address or a well-known place in Rome.">
                      <input className="input" value={place} onChange={(e) => setPlace(e.target.value)} placeholder="e.g. Circo Massimo" />
                    </Field>
                  ) : (
                    <AreaPicker area={area} onChange={setArea} />
                  )}
                  {fields.length > 0 && (
                    <Section title="Options" collapsible defaultOpen={false}>
                      <div className="grid grid-cols-2 gap-2">
                        {fields.map((f) => (
                          <Field key={f.key} label={f.unit ? `${f.label} (${f.unit})` : f.label}>
                            <input
                              className={`input ${f.numeric ? "num" : ""}`}
                              inputMode={f.numeric ? "decimal" : undefined}
                              value={values[f.key] ?? f.initial}
                              placeholder={f.initial === "" ? "optional" : undefined}
                              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            />
                          </Field>
                        ))}
                      </div>
                    </Section>
                  )}
                  <Section title={`What it runs (${uc.steps.length} steps)`} collapsible defaultOpen={false}>
                    <StepList steps={uc.steps} />
                  </Section>
                  <button className="btn w-full" disabled={busy || !useCaseReady(uc, { place, area })}>
                    {busy ? <Spinner /> : <Play className="h-4 w-4" aria-hidden="true" />}
                    {busy ? "Running…" : "Run this task"}
                  </button>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

/** The server's fixed plan, in order. Shown before a run and while it runs (no fake progress ticks). */
export function StepList({ steps }: { steps: string[] }) {
  return (
    <ol className="space-y-1 text-xs text-muted">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-2">
          <span className="num w-4 shrink-0 text-right text-2xs leading-[1.15rem]">{i + 1}</span>
          <span className="first-letter:uppercase">{s}</span>
        </li>
      ))}
    </ol>
  );
}
