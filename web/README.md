# Web: Urbs Gemina front end

React + TypeScript + Vite + Tailwind (the same stack Lovable generates), with a MapLibre + deck.gl 3D viewer.

## Run

```bash
cd web
npm install
npm run dev        # http://localhost:8080
npm test           # unit tests (vitest)
npm run typecheck  # strict TypeScript
```

With no `.env.local` the app calls the **live public tool API at the citizen tier** (no key in the browser).
With Lovable Cloud it goes through the `tools` edge function instead, which adds the office key for signed-in officers.
`VITE_SAMPLE_MODE=1` switches to built-in placeholder data (marked SAMPLE DATA). Settings in `.env.example`:

| Variable | What it is |
|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | Set by Lovable Cloud. Turns on sign-in and routes calls through the `tools` edge function |
| `VITE_TOOL_PROXY_URL` | Override for the edge function URL (default `<supabase>/functions/v1/tools`) |
| `VITE_TOOL_API_URL` | Public tool API used without Cloud (default: the Modal deployment) |
| `VITE_SAMPLE_MODE` | `1` = placeholder data, no network |
| `VITE_TREES_PMTILES_URL` | Tree crowns (default: the R2 copy; `off` to disable) |
| `VITE_BUILDINGS_PMTILES_URL` | G0 block model (`buildings.pmtiles`, 144 MB, not committed). Empty = the public copy on Cloudflare R2; `osm` = base-map OSM buildings; `/buildings.pmtiles` = a local copy in `web/public/` |
| `VITE_BASEMAP_STYLE`, `VITE_BASEMAP_STYLE_DARK` | Base map styles for the light and dark themes (OpenFreeMap Positron and Dark, no key). If unreachable the map falls back to a plain background |

## Look and feel

Italian PA design system (Titillium Web, PA blue, AA contrast) blended with a map-centred operational layout.
Two themes: light "Institutional" (default) and dark "Operations room" (button in the header).
Tokens, components, vocabulary and the decisions log are in [`docs/design-system.md`](docs/design-system.md).
New screens are assembled from `src/components/ui.tsx`; colours come from the tokens, never hard-coded.

## Screens

City view (whole-Rome 3D map, belief layers as H3 cells, area picker incl. drawing, time slider, uncertainty toggle) ·
Ask (ready-made tasks from `/use_cases`, orchestrator chat with run ids, sources, data kinds and map buttons) ·
Permit check (address → 300 m circle → context list → field range → downloadable cited report) ·
Scenario lab (river flood, heavy rain and sewers, heatwave, chemical plume, emergency access, road closure,
traffic event, antenna; key figures first, footprint on the map) · Data honesty · Sport · Admin (office tier).

## Contracts used

- Tool response envelope and tool names: `src/api/types.ts`, validated in `src/api/envelope.ts`.
- Orchestrator hand-over (`TwinQuestion` / `TwinAnswer`): `src/api/twin.ts`. The browser never sends the tier.
- Map actions shared with the voice agent (`voice/client_tools.json`): `src/lib/mapActions.ts`.
  The voice widget calls `window.urbsMap.dispatch({ tool, args })`; invalid actions and points outside Rome are dropped.
- Tool inputs follow `agents/tool_schemas_draft.json` until the tools stream publishes `twin/api/schemas/*.json`
  (e.g. `resolve_place {text}`, `context_check {point: [lon, lat]}`, `estimate_field {area}` with the 300 m circle as a
  64-vertex polygon). Envelopes with `status` `not_available` or `refused` show their `reason` instead of a result.
- Area ids: `city`, `municipio:1`..`municipio:15`, `zone:<CODE>`, or a GeoJSON polygon.
- Sport screen: `sports_facilities` and `sport_deserts` from the sports module (PR #5); manager updates go to
  `POST <proxy>/sports/manager_update` as `{facility_id, field, value, account_ref: "org:<slug>", confirmed_at}`.

## Lovable Cloud (login, roles, server function)

- `supabase/migrations/…_roles_and_manager_updates.sql`: `user_roles` (citizen | office; browsers can only read their own row)
  and `sports_manager_updates` (org accounts only).
- `supabase/functions/tools`: the only path from the browser to the back end. It reads the tier from `user_roles`
  (signed out = citizen), picks the tool API key for that tier, blocks office-only routes, sets the tier on `/ask`,
  and stores manager updates. Routing rules are in `supabase/functions/_shared/policy.ts` (unit-tested).
- Secrets to add in Lovable Cloud: `URBS_OFFICE_KEY` (office key of the tool API) and `ELEVENLABS_API_KEY`.
  Optional: `TOOL_API_URL` (default: the public Modal API), `TOOL_API_CITIZEN_KEY`, `ORCHESTRATOR_URL` (default `<api>/ask`),
  `ELEVENLABS_OFFICE_AGENT_ID`.
- Voice: the header button starts the public citizen agent directly; signed-in office users get the private office
  agent through `POST /voice/signed_url`. The agents move the map with the five client tools of `voice/client_tools.json`.
- To make someone an officer: insert a row `(user_id, 'office')` in `user_roles` from the Cloud dashboard.

## Lovable

Lovable cannot sync into a subfolder of an existing repository. To open this app in Lovable: zip the `web/` folder,
import it with "Upload code", then connect Git sync (Lovable creates its own repo). Mirror Lovable's edits back here with
`git subtree pull --prefix=web <lovable-repo> main --squash`.
