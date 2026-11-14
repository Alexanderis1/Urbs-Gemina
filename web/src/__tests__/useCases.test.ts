import { describe, expect, it } from "vitest";
import { buildUseCaseQuestion, paramFields, parseUseCases, useCaseTurnLabel, type UseCase } from "@/lib/useCases";

const briefing = {
  id: "municipio_briefing",
  title: { it: "Briefing mattutino del municipio", en: "Morning municipio briefing" },
  summary: { it: "Trasporti…", en: "Transit, traffic…" },
  needs: ["area"],
  params: {},
  steps: ["public transport delays", "air quality stations"],
};
const event = {
  id: "event_planning",
  title: { it: "Pianificazione evento", en: "Event planning" },
  summary: { it: "…", en: "…" },
  needs: ["place"],
  params: { attendees: 20000, radius_m: 400, tmax_c: null, discipline: "calcio" },
  steps: ["find the place"],
};

describe("ready-made use cases", () => {
  it("keeps well-formed entries and drops the rest", () => {
    const list = parseUseCases([briefing, event, { id: 5 }, null, { id: "x" }]);
    expect(list.map((u) => u.id)).toEqual(["municipio_briefing", "event_planning"]);
    expect(parseUseCases({ detail: "Not Found" })).toEqual([]);
  });

  it("describes each option with a plain label, its unit and its default", () => {
    const [uc] = parseUseCases([event]) as [UseCase];
    expect(paramFields(uc)).toEqual([
      { key: "attendees", label: "Attendees", unit: "", numeric: true, initial: "20000" },
      { key: "radius_m", label: "Radius", unit: "m", numeric: true, initial: "400" },
      { key: "tmax_c", label: "Tmax", unit: "°C", numeric: true, initial: "" },
      { key: "discipline", label: "Discipline", unit: "", numeric: false, initial: "calcio" },
    ]);
  });

  it("treats an option the server marks as text as text, even with no default", () => {
    const works = { ...event, id: "roadworks_check", params: { street: null, radius_m: 200 },
                    param_types: { street: "text", radius_m: "number" } };
    const [uc] = parseUseCases([works]) as [UseCase];
    expect(paramFields(uc).map((f) => [f.key, f.numeric])).toEqual([["street", false], ["radius_m", true]]);
    const body = buildUseCaseQuestion(uc, { place: "Via Nazionale", area: { type: "city" },
      values: { street: " Via Nazionale " }, language: "it", conversationId: null });
    expect(body.params).toEqual({ street: "Via Nazionale", radius_m: 200 });
  });

  it("builds the /ask body for a place: numbers as numbers, empty options left out", () => {
    const [uc] = parseUseCases([event]) as [UseCase];
    const body = buildUseCaseQuestion(uc, {
      place: " Circo Massimo ",
      area: { type: "city" },
      values: { attendees: "30000", radius_m: "400", tmax_c: "", discipline: "calcio" },
      language: "it",
      conversationId: "c1",
    });
    expect(body).toEqual({
      question: "Circo Massimo",
      language: "it",
      area: null,
      mode: "question",
      conversation_id: "c1",
      use_case: "event_planning",
      params: { attendees: 30000, radius_m: 400, discipline: "calcio" },
    });
  });

  it("builds the /ask body for an area and names the task in the officer's language", () => {
    const [uc] = parseUseCases([briefing]) as [UseCase];
    const input = { place: "", area: { type: "municipio", id: "5" } as const, values: {}, language: "en" as const, conversationId: null };
    expect(buildUseCaseQuestion(uc, input)).toMatchObject({ question: "Morning municipio briefing: Municipio V", area: "municipio:5", params: {} });
    expect(useCaseTurnLabel(uc, input)).toBe("Morning municipio briefing · Municipio V");
  });
});
