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

With no `.env.local` the app runs in **sample-data mode**: every tool response is generated locally,
marked `synthetic: true`, and the whole UI shows SIMULATED badges. Copy `.env.example` to `.env.local` to connect:

| Variable | What it is |
|---|---|
| `VITE_TOOL_PROXY_URL` | Edge function that holds the keys and the user's tier and forwards `POST /tools/<name>` to the tool API |
| `VITE_ASK_URL` | Orchestrator endpoint (defaults to `<proxy>/ask`) |
| `VITE_BUILDINGS_PMTILES_URL` | G0 block model from the city-model workstream. Empty = OpenStreetMap buildings from the base map |
| `VITE_BASEMAP_STYLE` | Base map style (OpenFreeMap, no key). If unreachable the map falls back to a plain background |

## Screens

City view (whole-Rome 3D map, belief layers as H3 cells, area picker incl. drawing, time slider, uncertainty toggle) ·
Ask (orchestrator chat with run ids, sources, data kinds and map buttons) · Permit check (address → 300 m circle →
context list → field range → downloadable cited report) · Scenario lab · Data honesty · Sport · Admin (office tier).

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

## Lovable

Lovable cannot sync into a subfolder of an existing repository. To open this app in Lovable: zip the `web/` folder,
import it with "Upload code", then connect Git sync (Lovable creates its own repo). Mirror Lovable's edits back here with
`git subtree pull --prefix=web <lovable-repo> main --squash`.
