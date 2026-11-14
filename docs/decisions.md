# Decisions: 3D viewer, hosting and build organisation

C=NN is a confidence score from 1 to 100. No time estimates.

## 1. 3D viewer: MapLibre-first, Cesium-first, or both

| | MapLibre GL + deck.gl | CesiumJS |
|---|---|---|
| What it is | 2.5D vector map: buildings are extruded footprints from vector tiles; deck.gl draws data layers on top | True 3D globe: streams 3D Tiles (meshes, point clouds, Gaussian splats) with terrain |
| Looks like | A clean "data map": flat-shaded block buildings, strong heatmaps, hexagons, arcs, moving dots | A "flight simulator" view: textured meshes, terrain relief, free camera |
| Whole city of LoD1 blocks | Strong. One PMTiles file, loads by zoom | Works, but needs a 3D Tiles tiling step and more GPU memory |
| Data overlays (belief grids, 300 m circles, live vehicles) | Its main strength | Possible, but draping vector data is reported as slow |
| LoD2 roofs from LiDAR | Via deck.gl `Tile3DLayer` in the same view | Native |
| Gaussian-splat landmarks | No official layer (C=55). Needs a separate splat viewer panel | Native in 3D Tiles since CesiumJS 1.139 |
| Weight in a Lovable React app | Light (C=65, not verified inside Lovable) | Heavier bundle and asset setup (C=60) |
| Licence | BSD / MIT | Apache 2.0. Cesium ion hosting is optional and paid for government use; self-hosting tiles avoids it |

**Why not both, depending on zoom? Yes, in one of two ways.**

| Way | How | Trade-off |
|---|---|---|
| A. One engine, two levels of detail (recommended) | MapLibre shows extruded blocks for the whole city. Past a zoom threshold, inside the LiDAR area, deck.gl's `Tile3DLayer` loads the LoD2 roof model. Same camera, no switch | Seamless. Splat landmarks open in a separate viewer panel |
| B. Two engines with a hand-over | MapLibre for the city. A button "open 3D detail" on a landmark or district opens a Cesium view at the same position | Not a continuous zoom: two WebGL canvases, two camera models (flat Mercator vs globe), double memory. Fine as an explicit switch, fragile as an automatic blend (C=75) |

Rule of thumb: if the demo is mostly **data on the city** (fields, air quality, traffic, context checks), go MapLibre-first with way A. If the demo is mostly **walking through reconstructed landmarks**, go Cesium-first. This project is the first kind, with landmarks as an accent, so the proposal is MapLibre-first, way A, plus a splat panel; upgrade to way B only if the splats turn out well enough to deserve it.

Gate: all of Rome renders smoothly in the chosen viewer inside the Lovable app on the demo laptop. No-go: drop to plain deck.gl layers.

## 2. Hosting: what Lovable can run and what it cannot

Lovable hosts the front end and a built-in backend ("Cloud") on Supabase technology: Postgres database, authentication, file storage, secrets, scheduled jobs and edge functions. Edge functions are short Deno (TypeScript) functions with hard limits: 256 MB memory, 2 seconds of CPU time per request, 150 seconds wall-clock on the free tier (400 on paid). There is no Python, no GPU and no always-on process. When credits run out the backend pauses.

| Backend part | What it needs | On Lovable? |
|---|---|---|
| Web app, login, citizen / office roles | Static hosting, auth, row-level security | **Yes** |
| Context layers and the 300 m check | A few tens of MB of vector data; a spatial query | **Yes**: as PostGIS SQL if the extension can be enabled on Lovable Cloud (C=60; a Supabase project of your own supports it), otherwise in the Python worker |
| Building tiles for the whole city | Static files of a few hundred MB served with range requests (size is a guess, C=40) | **Probably**: Cloud storage, or free object storage (Cloudflare R2) |
| Agent orchestration, Exa calls, ElevenLabs webhook | Mostly waiting on external APIs; little CPU | **Yes** (edge functions, keys in Secrets) |
| Cartoradio window read | Byte-range request plus decoding one small tile | **Yes** (edge function or the browser) |
| Live ingest of small feeds (GTFS-RT about 1 MB per pull, EEA hourly) | A scheduler and light parsing | **Partly**: scheduled jobs exist; stay inside the CPU limit |
| Belief layers (kriging / Gaussian process), rain-radar rasters | Python with NumPy/SciPy, 1-4 GB RAM, CPU for seconds to minutes | **No** |
| Traffic simulation (SUMO) | SUMO binary, 2-8 CPU cores, 4-8 GB RAM, runs for minutes | **No** |
| Field ray tracing (Sionna RT) | GPU with 8 GB or more (L4 / L40S class), runs for minutes | **No** |
| City model build, tiling, splat training | Offline batch on the workstation or a rented GPU; only results are uploaded | Not a hosting question |

**So: Lovable can host the app and the light backend, not the compute.** Three ways to add the compute:

| Option | Setup | Good | Bad |
|---|---|---|---|
| H1. Lovable + Modal (recommended) | Python "worker" on Modal: a small CPU service for tools, beliefs and ingest; a GPU function started on demand for ray tracing; a multi-core function for SUMO. Edge functions call it over HTTPS | Stable public URL for judges and the voice webhook; pay per second; $30 monthly free credit; GPU only while a job runs (L4 about $0.80/h, A100-80 about $2.50/h) | One more platform; cold starts of some seconds on first call |
| H2. Lovable + your workstation behind a tunnel | Same Python worker on the RTX 4060 Ti machine, exposed with a tunnel | Free; your own GPU | Demo depends on that machine, its network and the tunnel staying up; 8 GB VRAM caps ray-tracing size |
| H3. Lovable only | Everything in edge functions and SQL | Simplest | No belief layers beyond trivial ones, no simulation: the permit check works, the "twin" part does not |

Recommended: **H1**, with H2 as the fallback for GPU jobs if Modal credit runs out. Whatever is chosen, heavy results (grids, scenario outputs) are precomputed and cached so the live demo never waits on a cold GPU.

## 3. Build organisation (decided 13 Nov 2026)

Decided by Alessandro: no time-based scope cuts. The elements are built in parallel, one agent thread per workstream (WS1 to WS10, see `docs/workstreams.md`). The design hub owns the shared interfaces and records each workstream's final choices here.

## 4. Workstream decisions

| Workstream | Decision | Status |
|---|---|---|
| WS6 scenarios | Road closure runs on SUMO only, no simplified fallback model. Scenario kinds: antenna, population_exposure, road_closure (heavy) | Decided by Alessandro |
| Hub | Tool envelope gains top-level `status` (ok / not_available / refused) + `reason`, `cached`, and `not_available` as a data kind; `run_id` also hashes the driving config files | Agreed |
| Hub | Area ids: `city`, `municipio:<1-15>`, `zone:<CODE>`, or a GeoJSON polygon (300 m circle as a polygon). One parser in `twin/tools/area.py` | Agreed |
| WS10 sports | Facility type is public / school / private / unclassified; "private" only when a source states it, never inferred from appearing only in OSM or on the web | Agreed |
| WS4 tools | Tool list adds `permit_report`, `sports_facilities`, `sport_coverage`; `estimate_field` takes a point or an area | Agreed |
| Hub | Census sections handed over as `data/processed/census_sections.geojson` with fixed field names (`sez_id`, `residents`, `children_0_14`, `municipio`, `zone`), normalised by WS1 at ingest | Agreed |
| WS2 city model | Building heights from GlobalBuildingAtlas (CC BY-NC, full coverage) because the project is non-commercial; attribution in DATA_LICENSES and manifest. The rule is open *formats*, met by PMTiles | Decided by Alessandro |
| Hosting | Static tiles (buildings.pmtiles etc.) hosted on Cloudflare R2, public bucket `urbs-gemina-tiles` with CORS + Range; uploaded by `scripts/build_city_model.py --upload`; the app reads `VITE_BUILDINGS_PMTILES_URL` | Decided by Alessandro |
| Hub (rule) | Only traffic loop sensors may be simulated. Every other sensor or layer uses real sources + models + sensor fusion, labelled real or estimated. `sim_register` -> estimated register (OpenCelliD + OSM, EIRP fitted to Cartoradio, azimuth unknown, uncalibrated ~9 dB median error); `sim_emf_points` -> real ARPA points (DTS5887 table) + fused field; `sim_applications` dropped. What-if variants may hold hypothetical inputs | Decided by Alessandro |
| Hosting | buildings.pmtiles live at https://pub-92f3b81279724b93b2c580e6b7c1cb37.r2.dev/buildings.pmtiles (Range 206, CORS for Lovable + localhost) | Done 13 Nov |
| WS1/WS4 data | PRG has no WFS on Roma GeoServer: context_check queries `DIPAU:PrgSistemiRegole10000` by WMS GetFeatureInfo at runtime (component + NTA links at the point, plus sample points on the 300 m circle where needed). Rete Ecologica and Carta per la Qualità are ingested layers. SITAP art. 136 and OSM masts pending (server timeouts) | Agreed |
| Hosting | trees.pmtiles live at https://pub-92f3b81279724b93b2c580e6b7c1cb37.r2.dev/trees.pmtiles (CC BY 4.0 Meta/WRI); buildings.pmtiles replaced in place with height uncertainty, roof material and InSAR attributes | Done 13 Nov |
| Use cases (14 Nov, overnight) | Use cases are **playbooks** in `config/use_cases.yaml`: code runs a fixed list of tool calls, the model writes one narrative, the verifier checks it. Same pattern as the permit flow. Reachable by `use_case` on POST /ask and on the voice `ask_twin`, listed by GET /use_cases, and as a `run_use_case` tool in free chat | Claude, overnight; Alessandro to confirm |
| Use cases | New playbooks: municipio briefing, civil-protection alert, heat plan for the elderly, school/hospital risk check, event planning, citizen area info; antenna permit and sport deserts reachable the same way | Claude, overnight |
| Agents | Interface 7 `TwinQuestion` gains optional `use_case` and `params` (backwards compatible). `mode="briefing"` runs the `municipio_briefing` playbook: one model call instead of six agent loops | Claude, overnight |
| Agents | The model sees a compact view of tool outputs (no polygons, lists capped at 25, totals kept; `config/agents.yaml` model_view). One PGRA query was 15 MB in the dry run | Claude, overnight |
| WS4/WS6 glue | `run_scenario` adds a retrieval time to WS6 sources that lack one, and shows WS6's `hypothetical` inputs as `estimated` with a warning naming them as the officer's what-if values. Both crashed the API with HTTP 500 before | Claude, overnight |
| Verifier | Exempt from the figure check: the 112 emergency number, data-vintage years ("Copernicus 2018"), clock times and dates. A bare year or time next to a unit is still checked | Claude, overnight |
| Use cases (14 Nov, quality round) | Three more playbooks: industrial (Seveso) accident, air pollution episode, transport strike day. Untraceable lines are withheld one by one after the rewrite (officer told how many); voice answers carry no AI disclosure line (the voice agent says it first) | Claude |
| WS7 guardrails | Verifier `auto_cite`: a figure line without a tag is attached to the run of the same turn containing every figure on it; uncovered figures still blocked. Conditions: auto-cited lines marked in the trace, eval cases for figures paired with the wrong entity, identifiers never vouch for measurements | Agreed |
| Use cases (14 Nov, round 3) | Five more playbooks on new official Roma GeoServer layers: roadworks check, cold-weather plan (Piano Freddo), wildfire risk at the urban edge, nightlife check (movida zones + acoustic zoning, limits only, no noise sensor), citizen emergency info (civil-protection waiting areas). Heat, site-risk, civil-protection, Seveso and strike playbooks gain climate refuges, fountains, landslides, cavities, past interventions, plan areas and park-and-ride. The civil-protection intervention log drops health and person-assistance categories (home locations = personal data) | Claude, overnight |
| query_layer (14 Nov) | A static feature is also returned when a polygon covers the whole query area (a 500 m ring inside a PGRA flood zone used to return 0). Points are tested against a latitude-banded edge index: same answers, a municipio query on a 400k-vertex layer went from 83 s to about 1 s | Claude, overnight |
| Data kinds (14 Nov) | `query_layer` and `data_status` label a provider by its own entry in `twin/providers/registry.py` DATA_KIND first: Open-Meteo forecasts, CAMS, GloFAS and the GTFS timetable are `estimated`, not `real` (they were shown as real because their provider kind is "open") | Claude, overnight |
| Use cases (14 Nov, end to end) | Forecast steps read the forecast at `{when.tonight}` (03:00 Rome) or `{when.afternoon}` (15:00) from `config/use_cases.yaml` defaults.moments. `query_layer group_by` counts every feature in the area by a property (R4 fire areas, plan-area types, intervention kinds). The Roma GTFS-RT feed is frozen at the source since 13 Nov 18:27 UTC: transport playbooks add the timetable layer, labelled estimated. GET /use_cases gives `param_types` so the web form sends `street` as text | Claude, overnight |
| Language (14 Nov) | Italian first (Alessandro): agents answer in Italian unless the officer's text is clearly English (`agents/language.py` word heuristic; a place name keeps the client setting, Italian by default). Data kinds are named reale / stimato / simulato; problem lists and withheld-line notes are Italian too. Use-case fallbacks no longer echo the untraced figure | Claude, overnight |
