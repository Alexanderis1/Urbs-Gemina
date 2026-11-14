// The service writes its warnings and refusal reasons in English. The Italian app says the usual ones in
// Italian (numbers and names kept); a note it does not know is flagged so the screen can fold it away under
// "technical notes" instead of mixing English into Italian text. New service notes: add a line here.
import { getLang } from "@/lib/i18n";

export interface ServiceNote {
  text: string;
  /** False when the note stays in English inside the Italian app. */
  translated: boolean;
}

type Rule = [RegExp, (m: RegExpMatchArray) => string];

const IT: Rule[] = [
  [/^Place not found in Rome\.?$/i, () => "Luogo non trovato a Roma."],
  [/^(\d+) readings older than the layer time were skipped$/i, (m) => `${m[1]} rilevazioni più vecchie dell'ora del livello non sono state usate.`],
  [/^(\d+) readings fell outside the layer's cells and were not used$/i, (m) => `${m[1]} rilevazioni fuori dall'area del livello non sono state usate.`],
  [/^(\d+) sites lie outside the layer's area and were skipped$/i, (m) => `${m[1]} siti fuori dall'area del livello sono stati esclusi.`],
  [/^(\d+) simulated readings were refused: this layer is built from real data only$/i, (m) => `${m[1]} rilevazioni simulate escluse: questo livello usa solo dati reali.`],
  [/(?:the layer's )?uncertainty is uncalibrated/i, () => "Incertezza non ancora calibrata: l'intervallo è indicativo."],
  [/^no readings in the window: values are the prior only$/i, () => "Nessuna rilevazione recente: i valori sono la sola stima di partenza del modello."],
  [/^no radar readings in the window: rain is the forecast only$/i, () => "Nessuna immagine radar recente: la pioggia è solo la previsione."],
  [/^built from SIMULATED readings/i, () => "Costruito da rilevazioni SIMULATE: valori illustrativi, non misure."],
  [/^SIMULATED data: generated values, not measurements\.?$/i, () => "Dati SIMULATI: valori generati, non misure."],
  [/^Road speed fuses simulated traffic loops/i, () => "La velocità su strada usa spire di traffico simulate: conta con peso ridotto."],
  [
    /^Large area: (\d+) records, (\d+) returned, picked evenly across the area\..*$/i,
    (m) => `Area grande: ${m[1]} elementi, ne sono mostrati ${m[2]} scelti in modo uniforme. Scegli un'area più piccola (un municipio o una zona) per vederli tutti.`,
  ],
  [/^Only (\d+) of (\d+) places have readable opening hours.*$/i, (m) => `Solo ${m[1]} luoghi su ${m[2]} hanno orari leggibili; per gli altri gli orari non sono noti.`],
  [/^Air values are hourly estimates.*$/i, () => "I valori dell'aria sono stime orarie; i limiti di legge valgono su medie più lunghe, quindi il confronto è orientativo."],
  [/^Instantaneous worst-case estimate.*24-hour average\.?$/i, () => "Stima istantanea nel caso peggiore; il valore di attenzione è una media sulle 24 ore."],
  [/^Cartoradio value sits at its cap.*$/i, () => "Il valore Cartoradio è al suo massimo: leggilo come «15 V/m o più»."],
  [/^No Cartoradio cell near this point\.?$/i, () => "Nessuna cella Cartoradio vicino a questo punto."],
  [/^Future time: congestion is the expected pattern.*$/i, () => "Ora futura: il traffico è l'andamento atteso per quell'ora, non una previsione degli incidenti di oggi."],
  [/^Notices name lines, not places.*$/i, () => "Gli avvisi citano linee, non luoghi: il punto sulla mappa è la strada nominata nel testo, se c'è."],
  [/^The alerts feed has not been updated since (\S+) \(source side\)\.?$/i, (m) => `Il flusso degli avvisi non si aggiorna dal ${shortTime(m[1]!)} (lato fonte).`],
  [/^accessibility is 'not known' unless a source states it$/i, () => "L'accessibilità è «non nota» se nessuna fonte la indica."],
  [/^residents are the ISTAT 2021 census.*$/i, () => "I residenti sono quelli del censimento ISTAT 2021: dove le persone abitano, non dove sono durante il giorno."],
  [/^values are for the site's grid cell.*$/i, () => "I valori sono per la cella della griglia del sito (circa 0,11 km²), non per l'edificio esatto."],
  [/^Citizen reports are unverified.*$/i, () => "Le segnalazioni non sono verificate finché un operatore non le conferma; il grado di fiducia è una stima."],
  [/^Coordinates from the saved demo list are approximate\.?$/i, () => "Le coordinate dell'elenco salvato sono approssimative."],
  [/^Census age table not built.*$/i, () => "Tabella delle età del censimento non disponibile: mancano i conteggi degli anziani."],
  [/^Microclimate.*not applied.*$/i, () => "Microclima non applicato: la previsione è usata così com'è."],
  [/^(\d+) matches; the first is used\..*$/i, (m) => `${m[1]} risultati: è usato il primo. Controlla le alternative.`],
  [/^Geocoder unavailable.*$/i, () => "Ricerca degli indirizzi non disponibile: prova con le coordinate o un luogo salvato."],
  [/^Sensitive sites.*not built yet\.?$/i, () => "Il livello dei siti sensibili non è ancora disponibile."],
  [/^Census sections.*not built yet\.?$/i, () => "Le sezioni di censimento non sono ancora disponibili."],
  [/^No source connected for layer '([^']+)'\.?$/i, (m) => `Nessuna fonte collegata per il livello «${m[1]}».`],
  [/^Provider '([^']+)'.*not implemented or configured yet\.?$/i, (m) => `La fonte «${m[1]}» non è ancora configurata.`],
  [/^no weather forecast for this position$/i, () => "Nessuna previsione meteo per questa posizione."],
  [/^no air layer could be built\.?$/i, () => "Al momento non è stato possibile calcolare la qualità dell'aria."],
  [/^No baseline and no proposed antenna.*$/i, () => "Nessun dato di partenza e nessuna antenna proposta: niente da stimare."],
];

function shortTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function serviceNote(text: string): ServiceNote {
  if (getLang() !== "it") return { text, translated: true };
  const t = text.trim();
  for (const [re, say] of IT) {
    const m = t.match(re);
    if (m) return { text: say(m), translated: true };
  }
  return { text, translated: false };
}
