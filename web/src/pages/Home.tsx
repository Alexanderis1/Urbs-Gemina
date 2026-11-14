import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronRight, Database, Home as HomeIcon, ListChecks, Map as MapIcon, MapPin, MessagesSquare, Search, Sparkles, Trophy, type LucideIcon } from "lucide-react";
import { buildTwinQuestion, type TwinAnswer } from "@/api/twin";
import { AnswerText, AnswerTrace } from "@/components/Answer";
import { GlyphIcon } from "@/components/MarkerCard";
import { macroAreas } from "@/lib/services";
import { Callout, Skeleton, Spinner } from "@/components/ui";
import { StepList, USE_CASE_ICON, useUseCases } from "@/components/UseCases";
import { dispatchMapAction } from "@/lib/mapbus";
import { errorText } from "@/lib/errors";
import { getLang, texts, tr } from "@/lib/i18n";
import { PUBLIC_SCREENS, screenText, type ScreenId } from "@/lib/tiers";
import { useAskTwin } from "@/lib/useAskTwin";
import { buildUseCaseQuestion, residentWording, type UseCase } from "@/lib/useCases";

/** A topic the resident can ask about for an address. Comes from the service's task list; one is built in as a fallback. */
interface Topic {
  id: string;
  title: string;
  summary: string;
  icon: LucideIcon;
  useCase: UseCase | null;
}

const T = texts({
  en: {
    // Used when the service's task list has not arrived: the same question, asked in words.
    builtInTitle: "Around my address",
    builtInSummary: "Air, rain, public transport and health services nearby, in plain words.",
    builtInQuestion: (p: string) => `What should a resident know about the area around ${p}: air, rain, public transport and health services nearby?`,
    kicker: "Public information service",
    title: "Rome around you, now",
    lead: "Air, traffic, sport, culture and reports to the city. From open data, with the source of every fact. No account is needed.",
    services: "Services",
    askTitle: "Ask about your area",
    askLead: "Type your address or neighbourhood and get a short summary in plain words.",
    infoOnly: "Information only, not an alert service.",
    call112: "In an emergency call 112.",
    addressLabel: "Address or neighbourhood in Rome",
    addressPlaceholder: "Address or neighbourhood, e.g. Via Nazionale 194",
    looking: "Looking…",
    show: "Show my area",
    whatToKnow: "What do you want to know?",
    waiting: "Collecting the facts and checking every figure. This can take a minute.",
    lookedUp: "What is being looked up",
    noAnswer: "No answer this time",
    writtenBy: "Written by an AI assistant from the facts below · for information only",
    showOnMap: "Show it on the map",
    howWeKnow: "How we know this",
    explore: "Explore the city",
    exploreText: {
      city: "See air, rain, bus delays, hospitals and schools on the 3D map of Rome.",
      sport: "Find a sports facility near you, see the areas that have none, and try where a new one would help most.",
      ask: "Ask a question in your own words and get an answer with its sources.",
      honesty: "See where each piece of information comes from and how reliable it is.",
    } as Partial<Record<ScreenId, string>>,
  },
  it: {
    builtInTitle: "Intorno al mio indirizzo",
    builtInSummary: "Aria, pioggia, trasporto pubblico e servizi sanitari vicini, in parole semplici.",
    builtInQuestion: (p: string) => `Che cosa deve sapere un cittadino sulla zona intorno a ${p}: aria, pioggia, trasporto pubblico e servizi sanitari vicini?`,
    kicker: "Servizio pubblico di informazione",
    title: "Roma intorno a te, adesso",
    lead: "Aria, traffico, sport, cultura e segnalazioni alla città. Da dati aperti, con la fonte di ogni informazione. Non serve un account.",
    services: "Servizi",
    askTitle: "Chiedi della tua zona",
    askLead: "Scrivi il tuo indirizzo o il tuo quartiere e ricevi un breve riepilogo in parole semplici.",
    infoOnly: "Solo informazioni, non un servizio di allerta.",
    call112: "In caso di emergenza chiama il 112.",
    addressLabel: "Indirizzo o quartiere di Roma",
    addressPlaceholder: "Indirizzo o quartiere, ad es. Via Nazionale 194",
    looking: "Sto cercando…",
    show: "Mostra la mia zona",
    whatToKnow: "Che cosa vuoi sapere?",
    waiting: "Sto raccogliendo i dati e controllando ogni numero. Può volerci un minuto.",
    lookedUp: "Che cosa sto cercando",
    noAnswer: "Questa volta nessuna risposta",
    writtenBy: "Scritto da un assistente AI a partire dai dati qui sotto · solo a scopo informativo",
    showOnMap: "Mostra sulla mappa",
    howWeKnow: "Come lo sappiamo",
    explore: "Esplora la città",
    exploreText: {
      city: "Guarda aria, pioggia, ritardi dei bus, ospedali e scuole sulla mappa 3D di Roma.",
      sport: "Trova un impianto vicino a te, guarda le aree senza impianti e prova dove ne servirebbe uno nuovo.",
      ask: "Fai una domanda con parole tue e ricevi una risposta con le sue fonti.",
      honesty: "Scopri da dove viene ogni informazione e quanto è affidabile.",
    } as Partial<Record<ScreenId, string>>,
  },
});

const EXPLORE: { screen: ScreenId; icon: LucideIcon }[] = [
  { screen: "city", icon: MapIcon },
  { screen: "sport", icon: Trophy },
  { screen: "ask", icon: MessagesSquare },
  { screen: "honesty", icon: Database },
];

type State =
  | { status: "idle" }
  | { status: "busy"; title: string; steps: string[] }
  | { status: "done"; title: string; answer: TwinAnswer }
  | { status: "error"; text: string };

/**
 * The residents' front page, mobile first: the four macro-areas with their services, then a question about
 * one's own address, then the rest of the city. No account, no jargon.
 */
export default function Home() {
  const askTwin = useAskTwin();
  const t = tr(T);
  const builtIn: Topic = { id: "around", title: t.builtInTitle, summary: t.builtInSummary, icon: HomeIcon, useCase: null };
  // Tasks the service offers to residents for an address (it filters by who is asking).
  const fromService: Topic[] = useUseCases()
    .filter((u) => u.needs.includes("place"))
    .map((u) => ({ id: u.id, ...residentWording(u), icon: USE_CASE_ICON[u.id] ?? ListChecks, useCase: u }));
  const topics = fromService.length ? fromService : [builtIn];
  const [place, setPlace] = useState("");
  const [topicId, setTopicId] = useState<string | null>(null);
  const [state, setState] = useState<State>({ status: "idle" });
  const topic = topics.find((t) => t.id === topicId) ?? topics[0]!;
  const busy = state.status === "busy";

  async function submit() {
    const p = place.trim();
    if (!p || busy) return;
    const title = `${topic.title} · ${p}`;
    const body = topic.useCase
      ? buildUseCaseQuestion(topic.useCase, { place: p, area: { type: "city" }, values: {}, language: getLang(), conversationId: null })
      : buildTwinQuestion(t.builtInQuestion(p), { language: getLang() });
    setState({ status: "busy", title, steps: topic.useCase?.steps ?? [] });
    try {
      setState({ status: "done", title, answer: await askTwin(p, body) });
    } catch (e) {
      setState({ status: "error", text: errorText(e) });
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-4xl animate-rise-in space-y-4 px-4 py-5 md:space-y-5 md:px-5 md:py-8">
          <div className="space-y-1.5">
            <p className="label">{t.kicker}</p>
            <h1 className="text-2xl font-bold leading-tight md:text-3xl">{t.title}</h1>
            <p className="max-w-2xl text-sm text-muted md:text-base">{t.lead}</p>
          </div>
          <div aria-label={t.services} role="list" className="grid gap-3 md:grid-cols-2">
            {macroAreas().map((area) => (
              <section key={area.screen} role="listitem" className="overflow-hidden rounded border border-line bg-surface shadow-panel">
                <Link
                  to={PUBLIC_SCREENS.find((p) => p.id === area.screen)!.path}
                  className="flex items-center gap-3 px-3.5 py-3 transition-colors duration-150 hover:bg-sunken focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-link"
                >
                  <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${area.tone}`}>
                    <GlyphIcon glyph={area.glyph} className="h-6 w-6" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-lg font-bold leading-tight text-ink">{area.title}</span>
                    <span className="block text-sm text-muted">{area.summary}</span>
                  </span>
                  <ChevronRight className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
                </Link>
                <ul className="border-t border-line">
                  {area.services.map((sv) => (
                    <li key={sv.id} className="border-b border-line last:border-b-0">
                      <Link
                        to={sv.to}
                        className="flex min-h-12 items-center gap-3 px-3.5 py-2 transition-colors duration-150 hover:bg-primary-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-link"
                      >
                        <GlyphIcon glyph={sv.glyph} className="h-4 w-4 text-link" />
                        <span className="min-w-0 flex-1 text-sm font-semibold leading-snug text-link">{sv.title}</span>
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-4xl space-y-3 px-4 py-5 md:px-5">
          <div className="space-y-1">
            <h2 className="text-base font-bold">{t.askTitle}</h2>
            <p className="text-sm text-muted">{t.askLead}</p>
          </div>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div className="flex flex-wrap gap-2">
              <label className="relative min-w-0 flex-1 basis-72">
                <span className="sr-only">{t.addressLabel}</span>
                <MapPin className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" aria-hidden="true" />
                <input
                  className="input min-h-12 pl-10 text-base"
                  value={place}
                  onChange={(e) => setPlace(e.target.value)}
                  placeholder={t.addressPlaceholder}
                  autoComplete="street-address"
                />
              </label>
              <button className="btn min-h-12 px-6 text-base" disabled={busy || !place.trim()}>
                {busy ? <Spinner /> : <Search className="h-5 w-5" aria-hidden="true" />}
                {busy ? t.looking : t.show}
              </button>
            </div>
            {topics.length > 1 ? (
              <fieldset>
                <legend className="mb-2 text-sm font-semibold">{t.whatToKnow}</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {topics.map((t) => {
                    const on = t.id === topic.id;
                    return (
                      <label
                        key={t.id}
                        className={`flex cursor-pointer items-start gap-3 rounded border p-3 transition-colors duration-150 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-link ${
                          on ? "border-link bg-primary-soft" : "border-line hover:border-line-strong"
                        }`}
                      >
                        <input type="radio" name="topic" className="sr-only" checked={on} onChange={() => setTopicId(t.id)} />
                        <t.icon className={`mt-0.5 h-5 w-5 shrink-0 ${on ? "text-link" : "text-muted"}`} aria-hidden="true" />
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold leading-snug">{t.title}</span>
                          <span className="hint mt-0.5 block leading-snug">{t.summary}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            ) : (
              // One topic only: no choice to make, just say what the answer covers.
              <p className="flex items-start gap-2 text-sm text-muted">
                <topic.icon className="mt-0.5 h-4 w-4 shrink-0 text-link" aria-hidden="true" />
                <span>
                  <span className="font-semibold text-ink">{topic.title}.</span> {topic.summary}
                </span>
              </p>
            )}
          </form>
        </div>
      </section>

      <div className="mx-auto max-w-4xl space-y-6 px-4 py-5 md:px-5 md:py-6">
        <div aria-live="polite">
          {state.status === "busy" && (
            <article className="card animate-rise-in space-y-3">
              <h2 className="text-base font-bold">{state.title}</h2>
              <Skeleton lines={3} />
              <p className="hint">{t.waiting}</p>
              {state.steps.length > 0 && (
                <div className="rounded border border-line bg-sunken p-3">
                  <div className="label mb-1.5">{t.lookedUp}</div>
                  <StepList steps={state.steps} />
                </div>
              )}
            </article>
          )}
          {state.status === "error" && (
            <Callout tone="error" title={t.noAnswer}>
              {state.text}
            </Callout>
          )}
          {state.status === "done" && (
            <article className="card animate-rise-in space-y-3">
              <header className="space-y-1">
                <h2 className="text-base font-bold">{state.title}</h2>
                <p className="label flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  {t.writtenBy}
                </p>
              </header>
              <AnswerText text={state.answer.text} plain />
              {state.answer.map_actions.length > 0 && (
                <button type="button" className="btn-ghost" onClick={() => state.answer.map_actions.forEach((m) => dispatchMapAction(m))}>
                  <MapIcon className="h-4 w-4" aria-hidden="true" />
                  {t.showOnMap}
                </button>
              )}
              <details className="rounded border border-line">
                <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-link">{t.howWeKnow}</summary>
                <div className="px-3 pb-3">
                  <AnswerTrace a={state.answer} />
                </div>
              </details>
            </article>
          )}
        </div>

        <section aria-labelledby="explore" className="space-y-3">
          <h2 id="explore" className="text-base font-bold">
            {t.explore}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {EXPLORE.map((x) => {
              const s = PUBLIC_SCREENS.find((p) => p.id === x.screen)!;
              return (
                <Link
                  key={s.id}
                  to={s.path}
                  className="card group flex items-start gap-3 transition-colors duration-150 hover:border-link focus-visible:outline focus-visible:outline-2 focus-visible:outline-link"
                >
                  <x.icon className="mt-0.5 h-5 w-5 shrink-0 text-link" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1 text-sm font-semibold text-link">
                      {screenText("public", s.id).label}
                      <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden="true" />
                    </span>
                    <span className="mt-0.5 block text-sm text-muted">{t.exploreText[s.id]}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
        <p className="text-xs text-muted md:hidden">
          {t.infoOnly} <span className="font-semibold text-ink">{t.call112}</span>
        </p>
      </div>
    </div>
  );
}
