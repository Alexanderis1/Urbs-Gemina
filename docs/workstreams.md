# Urbs Gemina: parallel workstreams

One thread per workstream. Each brief is self-contained. The design hub thread ("Finalize the design plan element by element") owns the shared contracts and the design docs and merges decisions back into `docs/design-proposal.md`.

## Rules for every workstream

- Repo: `Alexanderis1/Urbs-Gemina`. Read `CLAUDE.md`, `docs/design-proposal.md` and `docs/decisions.md` first. Hard rules from `CLAUDE.md` apply (no personal data, real/estimated/simulated label on everything, numbers only from deterministic tools, thresholds only in `config/thresholds.yaml`, Cartoradio never committed, no blockchain, no time estimates).
- Work on your own branch and open your own PR. Test first in `tests/test_<stream>_*.py`; `python -m pytest` and `python -m mypy` (strict) must pass.
- Only edit the files your brief says you own. Shared files are **append-only**: add your entry, do not rewrite others' entries:
  - `data/manifest.json` (one entry per new source)
  - `pyproject.toml` (add your own optional-dependency group, e.g. `[project.optional-dependencies] model = [...]`; do not change `dependencies`)
  - `[tool.mypy] files` in `pyproject.toml`: when your folder first contains `.py` files, append it to the list in your own PR (e.g. `"voice"`). Do not add a folder that has no `.py` files on your branch, or mypy fails
- Contract changes (the interfaces below) go through the hub thread, not edited locally.
- Explain choices to Alessandro in plain language, give 2-3 options with a recommendation, and a confidence score (C=NN) when unsure.

## Data rule (13 Nov 2026)

**Only traffic loop sensors may be simulated.** Every other sensor or layer uses real existing sources, filled in with models and sensor fusion, labelled `real` or `estimated`. What-if variants may contain hypothetical inputs, flagged as such.

## Shared interfaces (frozen unless the hub changes them)

1. **Provider contract**: `twin/providers/base.py` (`Provider.describe() -> ProviderInfo`, `Provider.fetch(bbox, start, end) -> Iterable[Observation]`, `kind` in open | simulated | pa | restricted, `synthetic`, `redistribution`). Owned by the hub.
2. **Area argument**: every tool takes `area` as one of these, everywhere (tools, `map_actions`, UI, voice):
   - `"city"`: Roma Capitale;
   - `"municipio:<n>"` with `n` an integer 1 to 15 (municipio I = `municipio:1`);
   - `"zone:<code>"` with `code` the urban-zone code `code_zu` from layer `DIPPC:rc_zone_urbanistiche`, as a string, upper case (e.g. `zone:1A`);
   - a GeoJSON Polygon or MultiPolygon object in WGS84 (e.g. the 300 m circle around a point, as a 64-vertex polygon).
   Parsing lives in one place, owned by WS4 (`twin/tools/area.py`); others import it. Signature (fixed by the hub):
   `resolve_area(area: str | Mapping[str, Any]) -> Area`, with frozen dataclass `Area(id: str, kind: Literal["city","municipio","zone","polygon"], geometry: dict[str, Any] (GeoJSON, WGS84), bbox: BBox, area_km2: float)`; invalid ids raise `ValueError`. `id` is the canonical string (`"polygon:<sha256 of geometry, first 12 hex>"` for polygons). Heavy tools refuse areas above `heavy_tools_max_area_km2` (status `refused`).
3. **Tool response envelope** (every tool, JSON):
   `{ "run_id": str, "tool": str, "inputs": {...}, "result": {...}, "data_kinds": {"<layer>": "real|estimated|simulated"}, "sources": [{"id", "url?", "retrieved_at"}], "synthetic": bool, "warnings": [str] }`.
   Additions agreed 13 Nov (from WS6): top-level `"status": "ok" | "not_available" | "refused"` with `"reason": str` when not ok (`refused` = guardrail, e.g. heavy run on too large an area); top-level `"cached": bool`; `data_kinds` values may also be `"not_available"` for a missing input. Results that are not `ok` are never cached.
   `run_id` = SHA-256 of tool name + inputs + data snapshot hashes + hashes of the config files that drive the result (thresholds, emf_params, areas, scenarios, beliefs). Estimates carry `p5`, `p50`, `p95` and `calibration: "calibrated|uncalibrated"`.
4. **Tool list and HTTP API**: `POST /tools/<name>` on the tool API for `resolve_place`, `context_check`, `estimate_field` (point `[lon,lat]` or area), `query_layer` (area defaults to `city`), `run_scenario`, `legal_lookup`, `find_dataset`, `data_status`, `permit_report` (also `POST /reports/permit.md`), and the sports tools from WS10 (`sports_facilities`, `sport_coverage`; names final once WS10 confirms). Implemented by WS4 in PR #8. Final schemas published by WS4 in `twin/api/schemas/*.json`. Until then WS7's drafts in `agents/tool_schemas_draft.json` are the reference (`resolve_place {text} -> {lon, lat, municipio, urban_zone}`, `context_check {point:[lon,lat], radius_m}`); WS4 aligns with them or tells the hub what differs.
5. **Map data handoff**: WS1 writes each cleaned static layer to `data/processed/<layer>.geojson` (WGS84, git-ignored; GeoParquet copies optional), plus tiles (PMTiles) for the viewer from WS2; belief layers served as GeoJSON / H3 cell lists via `query_layer`.
   Shared copies of every cleaned layer (WS1, PR #11) are in `/mnt/project-files/data/processed/<layer>.geojson`; layer names in `config/ingest.yaml`, hashes in `data/manifest.json` → `snapshots`. Not yet available: SITAP art. 136, OSM masts.
   **Census sections** (`data/processed/census_sections.geojson`): WS1 joins ISTAT 2021 population to the section polygons and renames fields at ingest to `sez_id` (str), `residents` (int), `children_0_14` (int), `municipio` (int 1-15), `zone` (str). Consumers (WS4, WS6, WS10, WS5) read these names only; no guessing of ISTAT field names downstream.
6. **Answer contract**: `agents/prompts/answer_contract.md`.
7. **Orchestrator hand-over** (chat and voice both use it; WS7 implements, WS8 and WS9 consume), implemented by WS7 in `agents/contract.py` (PR #6); voice and web import from there:
   `ask(TwinQuestion{question, tier, language, area, mode, conversation_id}) -> TwinAnswer{text, verified, run_ids, sources, data_kinds, synthetic, missing, map_actions}`. `tier` (citizen | office) is set server-side, never by the caller or the model. `run_ids` are the tool envelope run ids.
8. **Map actions**: `map_actions` entries are `{"tool": <client tool name>, "args": {...}}`; client tools listed in `voice/client_tools.json` (`fly_to`, `show_area`, `show_layer`, `show_radius`, `open_screen`). WS8's map implements them for both chat and voice.

---

## WS1. Static data and ingest (Gate A)

- **Goal**: every whole-city context layer downloads, is cleaned of personal fields, gets a SHA-256 hash in the manifest and lands as GeoParquet. Live feed pullers (GTFS-RT, EEA hourly, rain radar, GBFS) store snapshots with a hash.
- **Owns**: `scripts/fetch_static_layers.py`, `twin/ingest/**`, `data/` layout, its manifest entries.
- **Respects**: manifest schema; drop contact fields (e.g. `ref-nome`, `ref-cell`, phone, e-mail of `DIPPC:241_ServiziSanitarieAssistenziali`) at ingest; layers that fail are marked "not available" (Gate A no-go rule).
- **Open choices**: storage (GeoParquet files vs Supabase PostGIS vs both); how live pullers are scheduled (Modal cron vs Lovable scheduled jobs vs workstation); care homes and playgrounds from OSM only.

## WS2. City model and 3D tiles (Gate B data side; G0, G1, G2)

- **Goal**: G0 LoD1 block model of all Rome (Overture/OSM footprints + heights, TINITALY terrain) as PMTiles, with the height check against Urban Atlas. Then G2 LoD2 roofs from the free MASE LiDAR along the Tiber, then G1 Gaussian-splat landmarks.
- **Owns**: `twin/model/**`, `scripts/build_*`, model outputs (git-ignored), validation report.
- **Respects**: one coordinate frame shared with the viewer (WGS84 / Web Mercator); simulations use G0/G2, never splats; validation metrics shown in the honesty panel.
- **Open choices**: height source (GlobalBuildingAtlas vs floors x 3.2 m); tile format for the chosen viewer (PMTiles vs 3D Tiles), coordinated with WS8; splat training on the 4060 Ti vs rented A6000; which landmarks.

## WS3. Providers and simulated sensors (Gate C)

- **Goal**: implement the providers in `config/providers.yaml`: `sim_register` (antenna sites seeded from OpenCelliD + OSM), `sim_emf_points`, `sim_applications`, `roma_gtfs_rt`, `eea_hourly`, `dpc_radar`, the restricted `cartoradio_grid` (byte-range read of the Rome window at runtime, never stored), extend `sim_loops`; plus the `data_status()` honesty listing. Gate C: switching a provider in YAML changes the data with no code change.
- **Owns**: `twin/providers/**` (except `base.py`), `twin/providers/registry.py`, `config/providers.yaml`, `config/emf_params.yaml`.
- **Respects**: `base.py` contract; fixed seed + version per simulator; every simulated record `synthetic=True`; Model A field names for the register; parameters in config with a `basis:` note.
- **Open choices**: how to cluster OpenCelliD cells into sites; EIRP table source; uncertainty band added to Cartoradio (C=60); whether to calibrate the synthetic register against Cartoradio.

## WS4. Deterministic tools, tool API and hosting (Gate D)

- **Goal**: `resolve_place`, `context_check` (300 m, all sensitive sites and constraints of Challenge 02), `estimate_field` (Cartoradio baseline + twin model, P5/P50/P95, exceedance probability), `query_layer`, `data_status`, the cited **permit report** builder, and the FastAPI tool API with published JSON schemas, deployed with a stable public URL.
- **Owns**: `twin/tools/**`, `twin/api/**`, `twin/modules/antennas/**`, `config/thresholds.yaml`, `config/areas.yaml`, deploy config (e.g. `deploy/`).
- **Respects**: tool response envelope; thresholds only from config; distance wording "context, not a ban"; role tiers enforced in the API (citizen sees aggregates only).
- **Open choices**: hosting (Modal vs workstation + tunnel; recommended Modal); spatial queries in Python (Shapely/GeoPandas) vs PostGIS; geocoder for `resolve_place` (Nominatim vs Roma's own street register).

## WS5. Belief layers (Gate E)

- **Goal**: per-cell mean + variance + timestamp layers for transit delay, road speed, air quality, rain, EMF, activity: prior, Bayesian update, decay, kriging on the residual; leave-one-station-out calibration on air quality; "uncalibrated" label where it fails.
- **Owns**: `twin/beliefs/**`, `config/beliefs.yaml` (new).
- **Respects**: consumes `Observation` from providers; served through `query_layer` (WS4 calls into `twin/beliefs`, so expose a plain Python function API); grid from `config/areas.yaml`.
- **Open choices**: grid (H3 res 9 vs 100 m grid matching Cartoradio vs census sections); method P1 (Kalman + kriging) vs P2 (spatio-temporal GP); which layers go live first.

## WS6. Scenario engine (Gate G)

- **Goal**: baseline vs variant with ranges on an operating area: antenna add/move (free-space city-wide, Sionna RT on a district), viewshed on protected skyline, population exposure (census), road closure with SUMO on one district, optionally accessibility (r5py), noise, shadow. Results cached so the demo never waits on a cold GPU.
- **Owns**: `twin/scenarios/**`, `config/scenarios.yaml` (new), heavy-job deploy functions.
- **Respects**: heavy-run area limit; "synthetic demand" label on traffic results; exposed through `run_scenario` (WS4 wires the endpoint; WS6 exposes `run(kind, area, change) -> envelope`).
- **Open choices**: which three scenarios first (suggested: antenna what-if, road closure, population exposure); SUMO via the existing open SUMO MCP server vs direct TraCI; Sionna on Modal GPU vs workstation.

## WS7. Agents, Exa and guardrails (Gate F)

- **Goal**: orchestrator, permit-context agent, scenario agent, data steward (Exa monitors + dataset scout), verifier that blocks any number without a run id or source; `legal_lookup` and `find_dataset` via Exa restricted to official domains; eval sets (grounding, refusal, prompt injection, tool accuracy). Gate F: a cited permit report where every number traces to a tool run.
- **Owns**: `agents/**`, `eval/**`, `docs/guardrails.md`.
- **Respects**: answer contract; calls tools only through the tool API schemas; web content enters as quoted data, no state-changing tool in the same turn; AI disclosure.
- **Open choices**: agent framework (plain tool-calling loop vs Claude Agent SDK vs LangGraph); which Claude model; where the orchestrator runs (Lovable edge function vs the Python API); verifier as code vs as an LLM pass.

## WS8. Front end (Lovable) and 3D viewer (Gate B view side)

- **Goal**: Lovable app synced into `web/`: City view (whole-city 3D map, layer switcher, area picker, time slider, uncertainty toggle), Ask (chat with sources and tool trace), Permit check (address -> 300 m circle -> context list -> field range -> downloadable cited report), Scenario lab, Data honesty panel, Admin (provider switch, thresholds, audit log). SIMULATED badges everywhere synthetic data shows. Supabase auth with citizen and office tiers.
- **Owns**: `web/**`, Supabase/Lovable Cloud config.
- **Respects**: tool API schemas (calls via edge functions holding keys); role tiers enforced server-side; AI disclosure banner.
- **Open choices**: viewer (MapLibre + deck.gl first vs Cesium first; recommended MapLibre with LiDAR roofs via `Tile3DLayer` and a separate splat panel); Lovable Cloud vs own Supabase project (PostGIS availability C=60).

## WS9. Voice agent (ElevenLabs)

- **Goal**: ElevenLabs conversational agent with one webhook tool `ask_twin` that goes through the same orchestrator and guardrails, client tools that move the map, a morning briefing per municipio and a citizen line. First sentence discloses it is an AI.
- **Owns**: `voice/**`.
- **Respects**: never bypasses the orchestrator; answer contract; citizen tier only sees aggregates.
- **Open choices**: Italian vs English vs both for the demo; voice embedded in the Lovable app (widget) vs phone number; how map-moving client tools talk to the viewer (coordinate with WS8).

## WS10. Sports facilities add-on (Challenge 04)

- **Goal**: merged facility map (GeoServer `DIPPC:243_ServiziSportivi`, open data `d30`, `GABSIN:piscine`, OSM, school-gym register), Exa scout per municipio and facility enrichment (disciplines, hours, accessibility with source URL and confidence), deterministic entity matching, twin indicators (transit access, residents within reach), "sport deserts" scenario, manager update flow. Gate S on one municipio first.
- **Owns**: `twin/modules/sports/**`, `agents/sports_scout/**`, `agents/sports_enrich/**`; the "Sport" screen is requested from WS8.
- **Respects**: web-derived fields labelled "from the web, unverified" until a manager confirms; organisational contacts only; accessibility "not known" unless a source states it.
- **Open choices**: Exa agent effort level; matching thresholds (name similarity, distance); which municipio for the first pass.

---

## Merge notes (hub)

- `pyproject.toml` `[tool.mypy] files`: after WS7 (#6) and WS9 (#2) merge, the value is `["twin", "scripts", "agents", "eval", "voice"]`.
- `.gitignore`: PR #1 and WS2 (#9) both add one; keep the union.
- Tier: `/ask` and `/voice/ask_twin` take the tier from the API key or agent secret, never from the request; orchestrator tool calls run in-process at the caller's tier (WS4, #8).
