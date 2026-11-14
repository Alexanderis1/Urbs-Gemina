import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Database, Home as HomeIcon, ListChecks, Map as MapIcon, MapPin, MessagesSquare, Search, Sparkles, Trophy, type LucideIcon } from "lucide-react";
import { buildTwinQuestion, type TwinAnswer } from "@/api/twin";
import { AnswerText, AnswerTrace } from "@/components/Answer";
import { Callout, Skeleton, Spinner } from "@/components/ui";
import { StepList, USE_CASE_ICON, useUseCases } from "@/components/UseCases";
import { dispatchMapAction } from "@/lib/mapbus";
import { errorText } from "@/lib/errors";
import { PUBLIC_SCREENS, type ScreenId } from "@/lib/tiers";
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

/** Used when the service's task list has not arrived: the same question, asked in words. */
const BUILT_IN: Topic = {
  id: "around",
  title: "Around my address",
  summary: "Air, rain, public transport and health services nearby, in plain words.",
  icon: HomeIcon,
  useCase: null,
};

const EXPLORE: { screen: ScreenId; icon: LucideIcon; text: string }[] = [
  { screen: "city", icon: MapIcon, text: "See air, rain, bus delays, hospitals and schools on the 3D map of Rome." },
  { screen: "sport", icon: Trophy, text: "Find a sports facility near you, and the areas that have none." },
  { screen: "ask", icon: MessagesSquare, text: "Ask a question in your own words and get an answer with its sources." },
  { screen: "honesty", icon: Database, text: "See where each piece of information comes from and how far to trust it." },
];

type State =
  | { status: "idle" }
  | { status: "busy"; title: string; steps: string[] }
  | { status: "done"; title: string; answer: TwinAnswer }
  | { status: "error"; text: string };

/** The residents' front page: type an address, pick a topic, read the answer. No account, no jargon. */
export default function Home() {
  const askTwin = useAskTwin();
  // Tasks the service offers to residents for an address (it filters by who is asking).
  const fromService: Topic[] = useUseCases()
    .filter((u) => u.needs.includes("place"))
    .map((u) => ({ id: u.id, ...residentWording(u), icon: USE_CASE_ICON[u.id] ?? ListChecks, useCase: u }));
  const topics = fromService.length ? fromService : [BUILT_IN];
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
      ? buildUseCaseQuestion(topic.useCase, { place: p, area: { type: "city" }, values: {}, language: "en", conversationId: null })
      : buildTwinQuestion(`What should a resident know about the area around ${p}: air, rain, public transport and health services nearby?`, { language: "en" });
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
        <div className="mx-auto max-w-4xl animate-rise-in space-y-5 px-5 py-8">
          <div className="space-y-2">
            <p className="label">Public information service</p>
            <h1 className="text-3xl font-bold leading-tight">What is happening around you in Rome</h1>
            <p className="max-w-2xl text-base text-muted">
              Type your address or neighbourhood. The city's digital twin answers from open data and says where each fact comes from. No account
              is needed.
            </p>
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
                <span className="sr-only">Address or neighbourhood in Rome</span>
                <MapPin className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" aria-hidden="true" />
                <input
                  className="input min-h-12 pl-10 text-base"
                  value={place}
                  onChange={(e) => setPlace(e.target.value)}
                  placeholder="Address or neighbourhood, e.g. Via Nazionale 194"
                  autoComplete="street-address"
                />
              </label>
              <button className="btn min-h-12 px-6 text-base" disabled={busy || !place.trim()}>
                {busy ? <Spinner /> : <Search className="h-5 w-5" aria-hidden="true" />}
                {busy ? "Looking…" : "Show my area"}
              </button>
            </div>
            {topics.length > 1 ? (
              <fieldset>
                <legend className="mb-2 text-sm font-semibold">What do you want to know?</legend>
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

      <div className="mx-auto max-w-4xl space-y-6 px-5 py-6">
        <div aria-live="polite">
          {state.status === "busy" && (
            <article className="card animate-rise-in space-y-3">
              <h2 className="text-base font-bold">{state.title}</h2>
              <Skeleton lines={3} />
              <p className="hint">Collecting the facts and checking every figure. This can take a minute.</p>
              {state.steps.length > 0 && (
                <div className="rounded border border-line bg-sunken p-3">
                  <div className="label mb-1.5">What is being looked up</div>
                  <StepList steps={state.steps} />
                </div>
              )}
            </article>
          )}
          {state.status === "error" && (
            <Callout tone="error" title="No answer this time">
              {state.text}
            </Callout>
          )}
          {state.status === "done" && (
            <article className="card animate-rise-in space-y-3">
              <header className="space-y-1">
                <h2 className="text-base font-bold">{state.title}</h2>
                <p className="label flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  Written by an AI assistant from the facts below · for information only
                </p>
              </header>
              <AnswerText text={state.answer.text} plain />
              {state.answer.map_actions.length > 0 && (
                <button type="button" className="btn-ghost" onClick={() => state.answer.map_actions.forEach((m) => dispatchMapAction(m))}>
                  <MapIcon className="h-4 w-4" aria-hidden="true" />
                  Show it on the map
                </button>
              )}
              <details className="rounded border border-line">
                <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-link">How we know this</summary>
                <div className="px-3 pb-3">
                  <AnswerTrace a={state.answer} />
                </div>
              </details>
            </article>
          )}
        </div>

        <section aria-labelledby="explore" className="space-y-3">
          <h2 id="explore" className="text-base font-bold">
            Explore the city
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
                      {s.label}
                      <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" aria-hidden="true" />
                    </span>
                    <span className="mt-0.5 block text-sm text-muted">{x.text}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
