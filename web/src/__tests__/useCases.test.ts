import { describe, expect, it } from "vitest";
import { buildUseCaseQuestion, forTier, paramFields, residentWording, parseUseCases, useCaseTurnLabel, type UseCase } from "@/lib/useCases";
import SAMPLE from "@/api/sampleUseCases.json";
import { setLang } from "@/lib/i18n";

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
    expect(body.params).toEqual({ place: "Via Nazionale", street: "Via Nazionale", radius_m: 200 });
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
      // The service looks the place up from params.place; the question alone is not enough.
      params: { place: "Circo Massimo", attendees: 30000, radius_m: 400, discipline: "calcio" },
    });
  });

  it("builds the /ask body for an area and names the task in the officer's language", () => {
    const [uc] = parseUseCases([briefing]) as [UseCase];
    const input = { place: "", area: { type: "municipio", id: "5" } as const, values: {}, language: "en" as const, conversationId: null };
    const body = buildUseCaseQuestion(uc, input);
    expect(body).toMatchObject({ question: "Morning municipio briefing: Municipio V", area: "municipio:5" });
    expect(body.params).toEqual({});
    expect(useCaseTurnLabel(uc, input)).toBe("Morning municipio briefing · Municipio V");
  });
});

describe("tasks by audience (sample mode; the live service filters by itself)", () => {
  const sample = parseUseCases(SAMPLE);

  it("the sample list carries who may run each task", () => {
    expect(sample.length).toBeGreaterThanOrEqual(11);
    expect(sample.every((u) => u.tiers && u.tiers.length > 0)).toBe(true);
  });

  it("residents get only the tasks marked for citizens; staff get all of them", () => {
    const citizen = forTier(sample, "citizen").map((u) => u.id);
    expect(citizen).toContain("citizen_area_info");
    expect(citizen).toContain("sport_deserts");
    expect(citizen).not.toContain("antenna_permit");
    expect(citizen).not.toContain("industrial_accident");
    expect(forTier(sample, "office")).toHaveLength(sample.length);
  });

  it("a task with no audience given (as the live service sends it) is kept: the service already filtered", () => {
    const [uc] = parseUseCases([{ id: "x", title: { en: "X" } }]) as [UseCase];
    expect(uc.tiers).toBeUndefined();
    expect(forTier([uc], "citizen")).toHaveLength(1);
  });
});

describe("wording for residents", () => {
  it("speaks to the resident, not about citizens", () => {
    const [uc] = parseUseCases([{ id: "citizen_area_info", title: { en: "Citizen information about their area" }, summary: { en: "Air, rain, transit…" } }]) as [UseCase];
    expect(residentWording(uc).title).toBe("Around my address");
  });
  it("keeps the service's own words for a task it does not know", () => {
    const [uc] = parseUseCases([{ id: "new_task", title: { en: "A new task" }, summary: { en: "What it does." } }]) as [UseCase];
    expect(residentWording(uc)).toEqual({ title: "A new task", summary: "What it does." });
  });
});

describe("resident wording in Italian", () => {
  it("speaks Italian", () => {
    setLang("it");
    try {
      const [uc] = parseUseCases([{ id: "citizen_emergency_info", title: { en: "E", it: "E it" }, summary: { en: "S", it: "S it" } }]) as [UseCase];
      expect(residentWording(uc).title).toBe("In caso di emergenza vicino a casa");
      const [other] = parseUseCases([{ id: "new_task", title: { en: "A new task", it: "Un nuovo compito" }, summary: { en: "What.", it: "Cosa fa." } }]) as [UseCase];
      expect(residentWording(other)).toEqual({ title: "Un nuovo compito", summary: "Cosa fa." });
    } finally {
      setLang("en");
    }
  });
});
