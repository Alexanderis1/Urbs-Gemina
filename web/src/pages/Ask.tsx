import { useEffect, useRef, useState } from "react";
import { MessagesSquare, Send, Sparkles } from "lucide-react";
import { StepList, UseCasePanel, useUseCases, type UseCaseRun } from "@/components/UseCases";
import { buildUseCaseQuestion, useCaseTurnLabel } from "@/lib/useCases";
import { buildTwinQuestion, type Language, type TwinAnswer } from "@/api/twin";
import { AnswerText, AnswerTrace } from "@/components/Answer";
import { Callout, Segmented, Skeleton } from "@/components/ui";
import { useAskTwin } from "@/lib/useAskTwin";
import type { Experience } from "@/lib/tiers";
import { errorText } from "@/lib/errors";

interface Turn {
  role: "user" | "assistant" | "error";
  text: string;
  answer?: TwinAnswer;
}

// Orchestrator hand-over (shared interface 7) through the edge function's /ask route,
// which sets the tier from the session and forwards to ORCHESTRATOR_URL.

/** Wording per experience: staff get operator language, residents get plain words. */
const COPY: Record<Experience, { title: string; lead: string; opening: string; placeholder: string; tasks: string; tasksLead: string; suggestions: string[] }> = {
  staff: {
    title: "Ask the twin",
    lead: "Answers come from tool runs and cited sources. Check the trace under each answer.",
    opening: "I am an AI assistant for Roma Capitale. I answer from tool runs and cited sources, and I support decisions rather than make them.",
    placeholder: "Ask about a place, a layer or a scenario…",
    tasks: "Ready-made tasks",
    tasksLead: "Fixed checklists of tool runs. The assistant writes the note; every figure is checked.",
    suggestions: [
      "What is within 300 m of Via Nazionale 194?",
      "How is the air quality in Municipio I right now?",
      "Which hospitals are in Municipio II?",
      "Where are the sport deserts for football?",
    ],
  },
  public: {
    title: "Ask about Rome",
    lead: "Ask in your own words. Each answer says where its facts come from.",
    opening: "I am an AI assistant based on the digital twin of Rome. I answer from open data and show my sources. My answers are for information only.",
    placeholder: "Ask about your neighbourhood, the air, the rain, transport…",
    tasks: "Common questions",
    tasksLead: "Pick one, give your address or area, and get the answer step by step.",
    suggestions: [
      "How is the air in Municipio I right now?",
      "Is it going to rain in Rome in the next hours?",
      "Which hospitals are in Municipio II?",
      "Where can I play football near Trastevere?",
    ],
  },
};

export default function Ask({ audience = "staff" }: { audience?: Experience }) {
  const copy = COPY[audience];
  const askTwin = useAskTwin();
  const [turns, setTurns] = useState<Turn[]>(() => [{ role: "assistant", text: copy.opening }]);
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [busy, setBusy] = useState(false);
  // Steps of the ready-made task that is running, shown while waiting.
  const [runningSteps, setRunningSteps] = useState<string[] | null>(null);
  const useCases = useUseCases();
  const conversationId = useRef(crypto.randomUUID());
  const endRef = useRef<HTMLDivElement>(null);

  const lastQuestionRef = useRef<HTMLDivElement>(null);

  // While waiting, keep the placeholder in view. When the answer arrives, put the question at the top
  // so the officer reads the answer from its first line (answers can be long).
  useEffect(() => {
    if (busy) endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    else lastQuestionRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [turns, busy]);
  const lastQuestion = turns.reduce((last, t, i) => (t.role === "user" ? i : last), -1);

  /** One round trip to the assistant: shows the request, waits, then shows the answer or the failure. */
  async function ask(shown: string, body: unknown, steps: string[] | null = null) {
    if (busy) return;
    setTurns((t) => [...t, { role: "user", text: shown }]);
    setBusy(true);
    setRunningSteps(steps);
    try {
      const answer = await askTwin(shown, body);
      setTurns((t) => [...t, { role: "assistant", text: answer.text, answer }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "error", text: `The assistant could not answer. ${errorText(e)}` }]);
    } finally {
      setBusy(false);
      setRunningSteps(null);
    }
  }

  async function send(question?: string) {
    const q = (question ?? text).trim();
    if (!q) return;
    setText("");
    await ask(q, buildTwinQuestion(q, { language, conversationId: conversationId.current }));
  }

  function runUseCase(r: UseCaseRun) {
    const input = { place: r.place, area: r.area, values: r.values, language, conversationId: conversationId.current };
    void ask(useCaseTurnLabel(r.useCase, input), buildUseCaseQuestion(r.useCase, input), r.useCase.steps);
  }

  const onlyOpening = turns.length === 1;

  return (
    <div className="flex h-full">
      {useCases.length > 0 && <UseCasePanel title={copy.tasks} subtitle={copy.tasksLead} useCases={useCases} language={language} busy={busy} onRun={runUseCase} />}
      <div className="flex h-full min-w-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          <header className="space-y-1">
            <h1 className="flex items-center gap-2 text-xl font-bold">
              <MessagesSquare className="h-5 w-5 text-link" aria-hidden="true" />
              {copy.title}
            </h1>
            <p className="hint">{copy.lead}</p>
          </header>
          <div className="space-y-3" aria-live="polite">
            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} ref={i === lastQuestion ? lastQuestionRef : undefined} className="flex animate-rise-in scroll-mt-4 justify-end">
                  <p className="max-w-[80%] whitespace-pre-wrap rounded bg-primary-soft px-3 py-2 text-sm leading-relaxed">{t.text}</p>
                </div>
              ) : t.role === "error" ? (
                <Callout key={i} tone="error" title="No answer">
                  {t.text}
                </Callout>
              ) : (
                <article key={i} className="card animate-rise-in space-y-3">
                  <div className="label flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                    AI assistant
                  </div>
                  <AnswerText text={t.text} plain={audience === "public"} />
                  {t.answer &&
                    (audience === "public" ? (
                      // Residents read the answer first; the evidence is one click away.
                      <details className="rounded border border-line">
                        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-link">How we know this</summary>
                        <div className="px-3 pb-3">
                          <AnswerTrace a={t.answer} />
                        </div>
                      </details>
                    ) : (
                      <AnswerTrace a={t.answer} />
                    ))}
                </article>
              ),
            )}
            {busy && (
              <div className="card animate-rise-in space-y-3">
                <div className="label flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                  AI assistant
                </div>
                <Skeleton lines={3} />
                <p className="hint">Running tools and checking figures…</p>
                {runningSteps && (
                  <div className="rounded border border-line bg-sunken p-3">
                    <div className="label mb-1.5">This task runs these steps, in order</div>
                    <StepList steps={runningSteps} />
                  </div>
                )}
              </div>
            )}
          </div>
          {onlyOpening && !busy && (
            <div className="flex flex-wrap gap-2">
              {copy.suggestions.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="btn-ghost btn-sm"
                  onClick={() => {
                    setText(q);
                    void send(q);
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>
      <div className="border-t border-line bg-surface">
        <form
          className="mx-auto flex max-w-3xl flex-wrap items-center gap-2 px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <div className="w-28 shrink-0">
            <Segmented
              label="Answer language"
              value={language}
              onChange={setLanguage}
              options={[
                { id: "en", label: "EN" },
                { id: "it", label: "IT" },
              ]}
            />
          </div>
          <input
            className="input min-w-0 flex-1"
            aria-label="Your question"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={copy.placeholder}
          />
          <button type="submit" className="btn" disabled={busy || !text.trim()}>
            <Send className="h-4 w-4" aria-hidden="true" />
            Ask
          </button>
        </form>
      </div>
      </div>
    </div>
  );
}
