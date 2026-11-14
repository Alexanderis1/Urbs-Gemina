# Urbs Gemina interface design

Short guide to how the front end looks and why. Code: `src/index.css` (tokens and component classes),
`tailwind.config.js` (class names), `src/lib/theme.ts` (tokens that code needs), `src/components/ui.tsx` (building blocks).

## Goal

Alessandro's brief (14 Nov 2026): professional and institutional; a mix of the Italian PA design system and
Palantir; a simulator, but not too futuristic; clear to understand; smooth animations.

What that means here:

| From the Italian PA design system (Designers Italia / Bootstrap Italia) | From operational tools (Palantir style) |
|---|---|
| Titillium Web type, PA blue `#0066CC`, navy `#17324D` | Map in the centre, controls docked at the sides |
| Plain language, labelled controls, AA contrast, visible focus | Dense but ordered panels, monospaced figures, run ids always visible |
| Square-ish corners (4 px), flat surfaces, thin borders | A dark "operations room" theme, status bar, short calm motion |

Not used on purpose: glows, neon, gradients on controls, glass effects, animated backgrounds, sci-fi fonts.

## Decisions log

1. **Two themes, one set of class names.** Light "Institutional" is the default (offices, projectors, print).
   Dark "Operations room" is one click away in the header and remembered per browser. Without a saved choice the
   system preference decides.
2. **Navy header in both themes.** The Bootstrap Italia header is PA blue; navy `#17324D` (its "dark" colour) is
   calmer next to a map and keeps PA blue free for actions and selection.
3. **PA blue replaces the old Roma red** as the action and selection colour, on screen and on the map.
   Red now only means danger or "over a limit".
4. **Fonts are self-hosted** (`@fontsource`), not loaded from Google: no third-party request, works offline,
   and it is what Italian privacy guidance asks of public sites.
5. **Left icon rail with labels** instead of a top menu: more room for the map, and every icon has a word under it
   so non-technical officers never guess.
6. **Data-honesty labels are a fixed vocabulary** (below) with a colour, a word and a shape each, so they also
   work in grey-scale and for colour-blind users. What-if has its own style (dashed, teal) and is no longer drawn
   as "simulated".
7. **Not branded as Roma Capitale.** No coat of arms or institutional logo. The top strip says it is an open-source
   prototype and carries the AI notice on every screen.
8. **Status bar at the bottom**: connection, tier, number of tool runs, last run id. It makes the audit trail
   visible without opening Admin.
9. **Interface language: Italian first, English as a switch** (changed 14 Nov 2026, see "Language"; it was English only before); the voice assistant speaks Italian. Labels use plain words:
   "Operating area", "Check context", "Compare".
10. **Scenario lab shows all eight scenario kinds**, grouped by theme (water, heat, hazard, mobility, antenna).
    A kind the service cannot run right now shows a clear notice with the server's reason instead of failing silently.
11. **Icons: lucide-react** (ISC licence, the Lovable default), 1.8 px stroke, always next to a word or with an
    `aria-label`.
12. **Results lead with people, then extent, then counts.** A scenario result opens with up to four key figures
    (residents affected first, then children and elderly, then area or depth, then counts). The full list sits below.
    When every model run gives the same number the range reads "same in every model run" instead of an empty bar.
13. **The map frames the result.** After a scenario run the camera fits the footprint that came back, so the
    officer never has to look for it.
14. **"Hypothetical" from the engine is shown as WHAT-IF.** One label for the user, whatever the engine calls it.
15. **Ask has a "Ready-made tasks" panel** on the left, filled from the service's use-case list (`/use_cases`).
    Each task shows what it will run before it runs. If the service has no list, the panel is hidden and Ask is a
    plain conversation.
16. **Answers are formatted, not raw text.** Headings, lists and bold are rendered; every `[run|src|data:…]`
    reference becomes a small chip, and the full citation list is folded under the answer.
17. **Traffic runs show one table: today, with the change, difference.** One row per measure (trip time, delay,
    hours lost, trips completed), middle value with its range under it. Traffic is simulated on a few blocks only,
    so the form asks for a drawn area; if the area is too large the server's own message is shown, once.
18. **Places are drawn only when their coordinates are in Rome**, and internal road ids are hidden when a street
    name is present.
19. **Every data layer is drawn on the 3D city.** The order is fixed in one place (`src/map/CityMap.tsx`,
    `src/lib/twinOverlay.ts`): base map, 3D buildings, data, then street and place names on top. A building never
    hides a dot; areas (cells, flood extents, sport zones) are see-through so the buildings under them stay
    readable (`AREA_ALPHA` in `src/lib/colors.ts`). Whole-city screens open at the widest zoom that still shows
    the buildings; further out, a small button brings them back.
20. **A sleeping service is not a failure.** The live service stops when idle and takes two to three minutes to
    wake. After a missing answer the screen waits for it and asks once more, and a blue strip says what is
    happening (`src/lib/retry.ts`, see 26).
21. **Map credits start folded** behind the (i) button so they never cover a legend; one click opens them.
22. **Sensor dots carry their value.** With 40 sensors or fewer each dot shows its number next to it; dots have a
    dark (light theme) or light (dark theme) edge so they stand out from the buildings. Values get plain names
    and units ("NO₂ (µg/m³)", not "no2"); a layer with several values per sensor gets a "Value shown" chooser.
23. **The City view opens on the twin's own estimates.** The first group of layers is "Live estimates (sensor
    fusion)": air, road speed, bus delay, rain, temperature, electric field, street activity, one value and its
    range per 170 m cell. A fused layer picked on "Whole city" opens on Municipio I (the whole city is about
    25,000 cells, more than one answer carries) and the camera frames the chosen area.
24. **One value everywhere is said in words**, not drawn as a colour scale from x to x.
25. **A layer the service does not carry is NOT AVAILABLE**, with the service's own first sentence as the reason.
    A large area comes back thinned (items picked evenly); the screen says how many of how many are shown.
26. **No call is started more than twice.** After a missing answer the service is woken with a light request and
    the call runs once more; a request the service cannot serve is not repeated (every start costs money).
27. **A long run is waited for, not repeated.** When a request runs long the service answers "still running" with
    a job id. The screen then reads that job every 4 seconds until the result is ready and shows it as a normal
    answer; a blue strip says "the live service is working on this request". Reading a job starts nothing. The
    wait ends after 15 minutes, or when the job is lost, with a plain sentence (`src/lib/jobs.ts`,
    `src/lib/errors.ts`). Through the staff gateway the job is read with the caller's own key (`/jobs/<id>`).
28. **No flat dots: 3D markers on the city model** (Alessandro, 14 Nov). Every point is a column rising from its
    exact spot, with a round glyph badge on top (places) or its value (readings); the column of a reading is as
    tall as its value. Columns are real 3D (buildings in front hide them); badges, values and the footprint on
    the ground always show. Sizes follow the zoom so a marker keeps its size on screen. More than 400 markers
    are drawn slim, and only the one under the pointer and the chosen one carry a badge
    (`src/lib/markers.ts`, `src/map/markers.ts`, glyphs in `src/map/markerGlyphs.ts`).
29. **Hover says what it is, a click says everything.** The card under the pointer has the glyph, the name, the
    type, the main value and the data label. A click or tap opens the detail card (a card at the right on a desk
    screen, a sheet from the bottom on a phone) with every fact in plain labels, all readings with their range,
    when it was updated, and "Zoom here". Staff also get the source's own fields. Contact details are never
    shown (`src/lib/resource.ts`, `src/components/MarkerCard.tsx`). A click on a marker is not also a click on
    the map under it.
30. **The residents' service is mobile first and organised in four macro-areas** (Alessandro, 14 Nov): Ambiente,
    Trasporti, Sociale, Segnala. With Home they are a bar at the bottom of a phone and tabs on a desk screen;
    the home page lists every service of each area as a question a resident would ask (`src/lib/services.ts`).
    Map screens put the map on top and the answer in a sheet under it (`MapScreen` in
    `src/components/CitizenMap.tsx`).
31. **"Here" on top of the whole city.** The resident's position (phone GPS, or a tap on the map; kept only in
    the browser tab) is a 3D marker; the answer for that point is one large value with its level in words, its
    likely range and the reference values, all given by the citizen tools (`air_here`, `emf_here`,
    `city_heatmap`, `transport_now`, `places_open`). The interface holds no threshold. When a citizen tool is
    not in the live service, the screen falls back to the layer tools and says what is missing
    (`src/lib/useCitizenData.ts`, `src/lib/here.ts`).


32. **A layer opens at once from its saved copy, then goes LIVE** (Alessandro, 14 Nov). The last answer of
    each layer is kept in the browser (IndexedDB, `src/lib/layerStore.ts`) and shown immediately, with the
    time of its data and "Caricamento dati live…". When the fresh answer arrives the green round **LIVE**
    badge appears with "Aggiornato alle hh:mm". Each layer has a life (`src/lib/liveLayer.ts`: 5 min for bus
    and traffic feeds, 10 for rain, 30 for air and fields, 12 h for registers, each with its basis); when it
    ends the badge goes and the layer is asked again. A copy still within its life is LIVE without a new
    request, and nothing is asked while the page is not on screen: the service is not woken for nobody.
    LIVE is about freshness only, the kind badge (REAL / ESTIMATED / SIMULATED) stays next to it. Never
    saved: refusals, the Cartoradio grid, the antenna register and single field measurements (sources that
    may not be passed on); the key holds the access tier and leaving the staff workspace wipes the copies.
    Used by the City view and by the city heatmap of Ambiente and Trasporti.

33. **Traffic is drawn on the roads, not as patches** (Alessandro, 14 Nov: "applied on the streets, even,
    with gradients, no dots"). On Trasporti the layer is painted along the main roads of Rome (28,470 roads
    from Overture Maps, ODbL, `public/roads-rome.json`, built by `scripts/build_web_roads.py`). Each street is
    cut in pieces of about 120 m; each piece takes the value of the twin's cells blended between the cell it
    is in and the six around it (`src/lib/roads.ts`), so the colour flows along the road. Width follows the
    road class and grows with the zoom. Traffic uses the colours people know from navigation maps (green,
    yellow, orange, red, dark red: `trafficColor`); bus delays keep the scale of every other map. The legend
    says in words that the colour is the average of the area the road crosses, not a reading on that road.
    Notices (roadworks, closures, strikes) stand on the map only in their own section, so the roads stay
    readable. If the road file cannot be read the cells are drawn as before. The "zoom in to see the 3D
    buildings" offer is off on whole-city maps.

34. **Smooth heatmaps, no hexagons** (Alessandro, 14 Nov: "a normal heatmap, not divided in hexagons").
    Area layers (air, field, heat, rain, crowds) are one picture laid on the city (`src/lib/heatRaster.ts`,
    drawn with a BitmapLayer in `src/map/heatLayer.ts`): every pixel blends the twin's cells around it with
    a soft bell under half a cell wide, so a single high cell keeps its peak and colours flow from place to
    place; the data fades out at its edge instead of ending in a line. It is the value field, not a density
    (a crowded area is not hotter because it has more cells). Less certain places are more see-through on the
    staff map; on the citizen maps good places are a light wash so the city stays readable. Hover and click
    still give the value of the cell under the pointer; the chosen place is a ring. The sport map's
    zoomed-out view is a smooth density picture of facilities.

## Two experiences

One twin, two front doors (decided 14 Nov 2026, on Alessandro's request for a clear division between public
users and city administration personnel). Which one a person gets is decided by their role, never by a
setting in the page: no sign-in or no staff role means the public service.

| | Public service ("Rome for residents") | Operations workspace (city staff) |
|---|---|---|
| Who | Anyone, no account | Signed-in personnel with the `office` role |
| Question it answers | "What is happening around me?" | "What is happening in the city, and what if?" |
| Header | PA blue, sections named in words across the top | Navy, "City staff" badge, icon rail on the left |
| Opens on | My area: one address field, one answer in plain words | City view: the 3D console with every layer |
| Sections | La mia zona, Mappa della città, Sport, Chiedi, I dati (My area, City map, Sport, Ask, About the data) | Città, Chiedi, Istanze, Scenari, Sport, Dati, Admin (City, Ask, Permit, Scenarios, Sport, Data, Admin) |
| Map | A short list of layers in plain words, whole city or a municipio | Every layer, drawn areas, last 24 hours, display options |
| Evidence | Folded under "How we know this" | Open: run ids, sources, the status bar with the run log |
| Theme | Always light | Light or dark "operations room" |
| Voice | Citizen line | Office assistant |
| Footer | "Information only. In an emergency call 112." | Connection, role, number of runs, last run id |

Rules:

1. **The colour of the header says where you are.** PA blue = public, navy = staff. Nothing else changes colour.
2. **Residents never see an office tool, not even greyed out.** Permit check, Scenario lab and Admin exist only
   in the workspace. Simulated layers (traffic loops, road speed) and raw model points are not in the public map.
3. **The public side leads with the person's address**, not with a tool. The topics offered come from the
   service's own list of tasks for citizens, so a new citizen task appears without a change here.
4. **The honesty labels stay on both sides.** REAL / ESTIMATED / SIMULATED / NOT AVAILABLE are public
   information too; only the run ids and the tool trace are folded away for residents.
5. **One door between the two:** "City staff sign-in" in the public header leads to `/staff` (magic link through
   Lovable Cloud). "Sign out" in the workspace leads back. A signed-in account without the staff role stays on
   the public side and is told why.
6. **Without Lovable Cloud (demo, local run)** the same page offers "Enter the staff workspace (demo)"; the
   choice is remembered in the browser. Data the service reserves for staff stays reserved either way.

Where it lives: `src/lib/tiers.ts` (who sees which screen, and each screen's address), `src/shell/PublicShell.tsx`
and `src/shell/StaffShell.tsx` (the two frames), `src/lib/layerCatalogue.ts` (layers and their wording per
experience), `src/pages/Home.tsx` and `src/pages/StaffAccess.tsx`. Screens shared by both (`CityView`, `Ask`)
take an `audience` prop and change wording and density, not behaviour.


## Language

Italian first, English as a switch (Alessandro, 14 Nov 2026; this replaces the earlier "UI in English" choice).

- The app opens in Italian. `IT | EN` in the header switches; the choice is remembered in the browser.
- Every text the interface writes exists in both languages, side by side, in the file that uses it:
  `const T = texts({ en: {...}, it: {...} })`, read with `tr(T)` (`src/lib/i18n.ts`). The compiler refuses a
  text that exists in one language only.
- Numbers follow the language (`locale()`): 12.345,6 in Italian, 12,345.6 in English.
- Text that arrives from the service is shown as it arrives: warnings, refusal reasons, place names. Assistant
  answers are requested in the interface language.
- Italian style follows Designers Italia: simple and direct, informal "tu" ("Scegli", "Riprova"), short
  sentences, no bureaucratic wording. Fixed vocabulary: livello, area operativa, reale / stimato / simulato /
  ipotesi / non disponibile, esecuzione, fonte, evidenze, incertezza, intervallo, istanza, sala operativa.
- Tests run in English (`src/__tests__/setup.ts`); each text library has an "in Italian" case.

## Tokens

Colours are CSS variables (`--c-*`, as `R G B`) so Tailwind opacity works: `bg-real/10`, `border-line`.

| Class name | Light | Dark | Use |
|---|---|---|---|
| `canvas` | `#F0F4F8` | `#0C1620` | page background |
| `surface` | `#FFFFFF` | `#172635` | panels, cards |
| `sunken` | `#F4F7FA` | `#111E2B` | table heads, stat tiles, footers |
| `line` / `line-strong` | `#D5DCE4` / `#A8B4C1` | `#2B3E52` / `#465C73` | borders / control borders |
| `ink` | `#17324D` | `#E8EEF4` | text |
| `muted` | `#556779` | `#A3B6C8` | secondary text |
| `primary` (+`hover`, `soft`) | `#0066CC` | `#0066CC` | button fills, selected background |
| `link` | `#0066CC` | `#6DB3FF` | text links, selected text, focus ring |
| `chrome` (+`deep`, `ink`, `muted`, `line`) | `#17324D` | `#0F1B27` | header and top strip |
| `real` | `#00794F` | `#3DD69B` | real data |
| `estimated` | `#8F5600` | `#F2B24C` | estimates, warnings |
| `simulated` | `#6E3FC4` | `#B595FF` | simulated (traffic loops only) |
| `whatif` | `#00707F` | `#4FD1DD` | user's hypothetical change |
| `danger` | `#C22A44` | `#FF7A8C` | errors, over a limit |

All text colours pass AA (4.5:1) on `surface`; `src/__tests__/theme.test.ts` checks it.

Type: Titillium Web 400 / 600 / 700. Figures and run ids: Roboto Mono (`.num`, `<code>`), tabular numbers.
Sizes: `text-2xs` 11 px labels, `text-xs` 13 px help, `text-sm` 15 px body in panels, `text-base` 16 px panel
titles, `text-xl` page titles and headline figures.

Spacing: 4 px grid. Panel padding 16 px, gap between sections 20 px, inside a section 8 px. Corners 4 px
(`rounded`), badges 2 px (`rounded-sm`). Shadows only on floating things (`shadow-panel`, `shadow-float`).

## Data-honesty vocabulary

Always use `KindBadge` (never hand-made chips). Words and hints live in `KIND_META` (`src/lib/theme.ts`).

| Label | Colour | Shape | Meaning |
|---|---|---|---|
| REAL | green | filled circle | open or official data |
| ESTIMATED | amber | half circle | model or crowd-sourced; always with a range |
| SIMULATED | violet | dashed circle | simulator output (traffic loops only) |
| WHAT-IF | teal, dashed border | diamond | the user's hypothetical change |
| NOT AVAILABLE | grey | struck circle | layer could not be read |
| SAMPLE DATA | amber fill | none | placeholder mode only (`SampleBadge`) |

Rules: every result block ends with `RunMeta` (label, run id, layer kinds, sources, warnings). An estimate is
never shown without its range (`RangeBar` or "x (range a to b)"). On the map, simulated items have a violet
outline and what-if items a teal one (`palette.simulated`, `palette.whatIf` from `useTheme()`).

## Layout

```
top strip      prototype notice · AI notice                         (chrome-deep)
header         logo · name            voice · theme · account       (chrome)
rail | screen                                                       (rail 72 px)
status bar     connection · tier · runs · last run id               (surface)
```

Two screen types:

- **Map screens** (City, Permit, Scenarios, Sport): `<Workspace panel={<Panel …/>}>` with the map filling the
  rest. Controls go in the left `Panel` in `Section`s, top to bottom in the order the officer works: what,
  where, when, then the action button. Results go either under the controls or in a second `Panel side="right"`
  (it slides in). Legends and the "what am I looking at" chip float on the map with `MapFloat`.
- **Page screens** (Ask, Data, Admin): `<Page title lead icon>` with cards and tables, max width 72 rem.

Building blocks (`src/components/ui.tsx`): `Workspace`, `Panel`, `Section` (optionally collapsible), `Field`
(label + control + hint), `Segmented` (2-4 choices), `Stat` (headline figure), `Callout` (info / warn / error),
`EmptyState`, `Skeleton`, `Spinner`, `LegendRamp`, `MapFloat`, `Page`.
CSS classes (`src/index.css`): `btn`, `btn-ghost`, `btn-quiet`, `btn-sm`, `input`, `check`, `label`, `hint`,
`num`, `card`, `table`, `map-float`, `skeleton`.

One primary button (`btn`) per panel: the action that runs the tool. Everything else is `btn-ghost` or
`btn-quiet`.

## Motion

Short and functional, never decorative.

| What | Class | Timing |
|---|---|---|
| New result, card, map float | `animate-rise-in` | 220 ms, 6 px rise |
| Right panel | `animate-slide-in-right` | 240 ms |
| Messages, section content | `animate-fade-in` | 180 ms |
| Loading | `skeleton` / `Spinner` | shimmer 1.6 s |
| Hover, selection, range bars | `transition-colors` / `transition-all` | 150 ms / 500 ms |
| Live dot, voice listening | `animate-pulse-ring` | 1.6 s |
| Map camera | MapLibre `flyTo` | default easing |

`prefers-reduced-motion` switches all of it off.

## Accessibility

AA contrast in both themes; one focus ring everywhere (`:focus-visible`, 2 px `link` colour); controls at least
32 px high (36 px for buttons and inputs); every input inside a `Field` or with an `aria-label`; icons are
`aria-hidden` when next to text; status changes use `role="status"` / `role="alert"`; a "Skip to content" link;
colour is never the only signal (badge shapes, icons on warnings).

## Map colours

`useTheme().palette` (`MAP_PALETTE` in `src/lib/theme.ts`) gives deck.gl colours per theme: `accent`
(selection, drawn areas, radius), `point`, `inactive`, `simulated`, `whatIf`, `good`, `bad`. Do not hard-code
RGB values in screens. The value ramp for belief layers stays in `src/lib/colors.ts`.
Base map: OpenFreeMap Positron (light) and Dark (dark); plain background if it cannot be reached.
