// The residents' services, grouped in four macro-areas (Alessandro, 14 Nov 2026): the home page lists them,
// the navigation bar opens them. Each service is a question a resident would ask, and opens the screen that answers it.
import { texts, tr } from "@/lib/i18n";
import { screenPath, screenText, type ScreenId } from "@/lib/tiers";
import type { Glyph } from "@/map/markerGlyphs";

export interface CitizenService {
  id: string;
  title: string;
  summary: string;
  glyph: Glyph;
  /** Address inside the macro-area screen. */
  to: string;
}

export interface MacroArea {
  screen: Extract<ScreenId, "environment" | "transport" | "social" | "report">;
  title: string;
  summary: string;
  glyph: Glyph;
  /** Tailwind classes of the area's colour chip (same hue on the home page and in the screen header). */
  tone: string;
  services: CitizenService[];
}

const T = texts({
  en: {
    environment: "Air and electromagnetic fields where you are.",
    transport: "Traffic, roadworks, closures and strikes.",
    social: "Sport and culture at the time you choose.",
    report: "Tell the city what you see, with a photo.",
    air: ["How is the air here?", "The pollution at your position now, on the map of Rome"],
    emf: ["Electromagnetic fields here", "The exposure to antennas at your position"],
    traffic: ["Traffic now and in the next hours", "Where the roads are slow, and where they will be"],
    events: ["Roadworks, closures and strikes", "What is changing public transport and roads today"],
    sport: ["Where can I do sport?", "Facilities for the sport, day and time you choose"],
    museums: ["Museums and galleries", "Which ones are open on the day and time you choose"],
    flood: ["Flooding or a sewer problem", "Water on the street, a blocked drain"],
    pothole: ["A hole in the road", "Damaged road or pavement"],
    trafficReport: ["Accident, traffic or transport problem", "A crash, a jam, a bus or metro fault"],
    roadworks: ["A building site not on the map", "Works that the map does not show yet"],
    publicEvent: ["A public event not on the map", "A market, a concert, a street party"],
  },
  it: {
    environment: "Aria e campi elettromagnetici dove sei.",
    transport: "Traffico, cantieri, chiusure e scioperi.",
    social: "Sport e cultura all'ora che scegli.",
    report: "Segnala alla città quello che vedi, con una foto.",
    air: ["Com'è l'aria qui?", "L'inquinamento nella tua posizione adesso, sulla mappa di Roma"],
    emf: ["Campi elettromagnetici qui", "L'esposizione alle antenne nella tua posizione"],
    traffic: ["Traffico adesso e nelle prossime ore", "Dove le strade sono lente e dove lo saranno"],
    events: ["Cantieri, chiusure e scioperi", "Che cosa cambia oggi per strade e trasporto pubblico"],
    sport: ["Dove posso fare sport?", "Impianti per lo sport, il giorno e l'ora che scegli"],
    museums: ["Musei e gallerie", "Quali sono aperti nel giorno e all'ora che scegli"],
    flood: ["Allagamento o problema di fogna", "Acqua in strada, un tombino ostruito"],
    pothole: ["Una buca in strada", "Strada o marciapiede danneggiati"],
    trafficReport: ["Incidente, traffico o problema dei mezzi", "Un incidente, un ingorgo, un guasto di bus o metro"],
    roadworks: ["Un cantiere che non è sulla mappa", "Lavori che la mappa non mostra ancora"],
    publicEvent: ["Un evento pubblico che non è sulla mappa", "Un mercato, un concerto, una festa di quartiere"],
  },
});

type Key = Exclude<keyof ReturnType<typeof text>, "environment" | "transport" | "social" | "report">;
function text() {
  return tr(T);
}

export function macroAreas(): MacroArea[] {
  const t = text();
  const service = (base: string, id: string, key: Key, glyph: Glyph, query: string): CitizenService => {
    const [title, summary] = t[key] as [string, string];
    return { id, title, summary, glyph, to: `${base}?${query}` };
  };
  const area = (screen: MacroArea["screen"], glyph: Glyph, tone: string, build: (base: string) => CitizenService[]): MacroArea => ({
    screen,
    title: screenText("public", screen).label,
    summary: t[screen],
    glyph,
    tone,
    services: build(screenPath("public", screen) ?? "/"),
  });
  return [
    area("environment", "air", "bg-real/10 text-real", (b) => [
      service(b, "air", "air", "air", "vista=aria"),
      service(b, "emf", "emf", "field", "vista=campi"),
    ]),
    area("transport", "bus", "bg-primary-soft text-link", (b) => [
      service(b, "traffic", "traffic", "traffic", "vista=traffico"),
      service(b, "events", "events", "roadworks", "vista=eventi"),
    ]),
    area("social", "sport", "bg-simulated/10 text-simulated", (b) => [
      service(b, "sport", "sport", "sport", "cosa=sport"),
      service(b, "museums", "museums", "museum", "cosa=musei"),
    ]),
    area("report", "report", "bg-estimated/10 text-estimated", (b) => [
      service(b, "flood", "flood", "flood", "tipo=flood"),
      service(b, "pothole", "pothole", "pothole", "tipo=pothole"),
      service(b, "traffic", "trafficReport", "incident", "tipo=traffic"),
      service(b, "roadworks", "roadworks", "roadworks", "tipo=roadworks"),
      service(b, "public_event", "publicEvent", "event", "tipo=public_event"),
    ]),
  ];
}
