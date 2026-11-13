# Urbs Gemina: design proposal and options

Status: proposal, 13 Nov 2026. Companion documents: `docs/data-inventory.md` (full data inventory, endpoints, prices) and `docs/feasibility-report.md` (literature).

How to read: **C=NN** is a confidence score from 1 to 100 on anything not verified. **[inf]** marks my own design judgement. Plans are ordered steps with go/no-go gates; there are no time or effort estimates.

---

## 1. What we are building

A digital twin of **the whole city of Rome**, built only from public data, that a public-administration officer can question, watch live, and use to test "what if" scenarios. Districts are a working unit inside it, not the limit of it.

Decisions already taken (by you):

| Decision | Consequence in the design |
|---|---|
| Whole city first; districts simplify heavy tasks | Every data layer covers all of Rome. Heavy simulations run on an "operating area" (a municipio, an urban zone or a drawn polygon) |
| Roma Capitale cannot share loop-sensor data and holds no antenna data | **Simulated sensors behind the same interface as real ones.** The PA later swaps in its own access without code changes |
| **Only traffic loops may be simulated** (13 Nov 2026, supersedes section 8 for every other simulator) | Antenna sites, EMF values and every other layer come from real existing sources (OpenCelliD, OSM, Cartoradio, the ARPA station, EEA, GTFS-RT, radar...) combined with models and sensor fusion, labelled `estimated` where modelled. No synthetic records outside `sim_loops` |
| Own solution that also satisfies Challenge 02 | The antenna module is one application of the twin, not the whole product |
| No Avalanche | Provenance is a local hash manifest plus git history. No blockchain |
| Target Exa, ElevenLabs and Lovable | Each gets a real job in the core flow (section 11) |
| Technically valid, not a cheap demo | Every layer ships with a validation metric and a visible "real / estimated / simulated" label |
| Cannot afford both Pléiades and Vexcel | The design needs no data purchase (section 6 explains why the stereo buy is dropped) |
| cartoradio.it may be used for the proposal; Roma Capitale will obtain explicit consent from cartoradio for its own use | The national 100 m field grid becomes the **city-wide EMF baseline** (section 9a), handled as a restricted provider: fetched at runtime, never copied into the public repo |

Hackathon rules that shape it: open-source code, open-format data, no personal data exposed, AI agents required, a working live flow.

---

## 2. Who uses it and for what

| User | Example question | What the twin does |
|---|---|---|
| Urban-planning officer (antenna permits) | "An operator applies for a mast at this address. What is around it?" | 300 m context check on official layers, estimated field with a range, cited report |
| Environment officer | "Where is NO2 worst right now and how sure are we?" | Air-quality belief layer with uncertainty, station values, sources |
| Mobility officer | "What happens to bus delays if we close this road on Saturday?" | Traffic scenario on the affected district, before/after indicators |
| Municipio staff | "Brief me on my municipio this morning" | Spoken briefing (voice agent) from live layers and news alerts |
| Citizen (public tier) | "Is there an antenna near my child's school?" | Aggregated public answer, no office-only technical data |

---

## 3. System overview

```
 PUBLIC DATA + SIMULATED SENSORS                         USERS
 --------------------------------                        -----
 open feeds   simulated feeds   (later) PA feeds         officer / citizen
      \            |                /                    browser      voice
       +-----------+---------------+                        |           |
                   |                                        v           v
          [1] PROVIDER ADAPTERS  (one interface)      [6] LOVABLE   ELEVENLABS
                   |                                   front end      agent
                   v                                        |           |
          [2] TWIN STORE                                    +-----+-----+
              - city model (buildings, terrain, splats)           |
              - context layers (PRG, constraints, schools...)     v
              - observations (time series)               [5] AGENT LAYER
              - belief layers (mean + uncertainty)           orchestrator + tools
                   |                                        + guardrails + Exa
                   v                                              |
          [3] TOOL API  (deterministic: geometry, thresholds) <---+
                   |
                   v
          [4] SCENARIO ENGINE  (traffic, EMF, others; per operating area)
```

The key rule: **numbers come from tools, words come from the model.** The agent never computes a distance, a field value or a legal threshold itself.

---

## 4. The central idea: providers you can swap

Every data source, real or simulated, is a **provider** with the same interface. Each layer has one active provider chosen in a config file.

```python
class Provider(Protocol):
    id: str                      # "roma_gtfs_rt", "sim_loops", "pa_loops"
    kind: Literal["open", "simulated", "pa"]
    def describe(self) -> ProviderInfo          # licence, cadence, synthetic flag, schema
    def fetch(self, area, t0, t1) -> Iterable[Observation]

@dataclass
class Observation:
    entity_id: str        # e.g. "urn:ngsi-ld:TrafficFlowObserved:RM-loop-017"
    entity_type: str      # Smart Data Models type where one exists
    geometry: dict        # GeoJSON
    observed_at: datetime
    values: dict          # {"intensity": 412, "averageVehicleSpeed": 31.5}
    sigma: dict           # measurement uncertainty per value
    source_id: str        # provider id + snapshot hash
    synthetic: bool       # True for every simulated record
```

```yaml
# providers.yaml  (the only file the PA edits to go live)
traffic_flow:       sim_loops          # later: pa_datex   (Roma Mobilità DATEX II node)
antenna_register:   sim_register       # later: pa_register (Model A applications)
emf_measurements:   sim_emf_points     # later: arpa_points
transit:            roma_gtfs_rt       # real, open
air_quality:        eea_hourly         # real, open
```

Why this is the right shape [inf, C=80]:

- The same code path is exercised with simulated data today and real data later, so the demo is honest about what is ready.
- Entities follow NGSI-LD / Smart Data Models naming, the pattern used by the EU Local Digital Twin toolbox, so a context broker can be added later without redesign.
- Roma Mobilità states it plans a DATEX II node for its sensors. A `pa_datex` provider is therefore a realistic integration point (C=60 on the node's timing).
- `synthetic: true` travels with every record up to the UI, where it becomes a visible **SIMULATED** badge. Nothing simulated can be mistaken for a measurement.

---

## 5. City model: whole city, with districts as operating areas

**Spatial units**

| Unit | Source | Use |
|---|---|---|
| Whole city (Roma Capitale boundary) | Roma GeoServer `DIPPC:210_RomaCapitale_Municipi` (dissolved) | Default extent of every layer |
| 15 municipi | same layer | Officer scope, briefings, role-based access |
| 155 urban zones | `DIPDIT:ZoneUrbanistiche` | Default operating area for simulations |
| Census sections (13,656) | Roma GeoServer / ISTAT 2021 | Population exposure |
| H3 hex grid, resolution 9 city-wide (about 0.1 km² per cell) | computed | Belief layers. Finer grid or raster only inside an operating area |

Every tool takes an `area` argument: `city`, a municipio id, an urban-zone id or a polygon. Heavy tools (micro traffic simulation, ray tracing) refuse `city` and propose a district or a coarser model instead. That refusal is part of the guardrails.

**Geometry tiers**

| Tier | What | Coverage | Cost | Status |
|---|---|---|---|---|
| G0 | LoD1 block model: Overture/OSM footprints + heights (GlobalBuildingAtlas; fallback floors × 3.2 m) on TINITALY terrain, AGEA orthophoto as ground texture | **Whole city** | Free | Core |
| G1 | Gaussian-splat landmarks from MegaScenes camera poses (Pantheon, Forum, Piazza Navona, Vittoriano, St Peter's), georeferenced to the orthophoto | Landmarks | GPU rental only | Recommended |
| G2 | True surface model from the free national LiDAR (1 m, CC BY 4.0), then LoD2 roofs | About 16 km² along the Tiber in the centre | Free | Recommended, see section 6 |
| G3 | Vexcel aerial hero tile | 1–2 km² | $35–115 per km² | Not recommended: licence for open publication unclear (C=60 that it is internal-use only) |

G0 is the twin. G1 and G2 are detail layers that plug into the same viewer and the same coordinate frame. Simulations use G0 (or G2 where it exists), never the splats, because splats are appearance, not measured geometry.

**Validation shown in the UI**

| Layer | Metric | Reference |
|---|---|---|
| G0 heights | Mean error, bias, share of buildings with a height | Copernicus Urban Atlas Building Height 2012 (10 m raster, so flag its age) |
| G1 splats | PSNR / SSIM on held-out photos; georeferencing residual in metres at unused control points | Withheld images; AGEA orthophoto |
| G2 surface model | Roof-plane fit residual; and, where LiDAR exists, the LiDAR heights become the reference to score G0 against | LiDAR itself; known landmark heights |

---

## 6. True 3D for the centre (G2): skip the stereo purchase, use the free LiDAR

**Result of the archive check (13 Nov 2026): a stereo set of Rome could not be confirmed, and buying one would not fit this project anyway.**

| Finding | Detail | C |
|---|---|---|
| Existence | Not confirmed. Every commercial catalogue (Airbus OneAtlas, Apollo, UP42, SkyFi) needs a login. Only single cloud-free scenes were seen (Pléiades Neo 30 Jun 2024, Pléiades 1B 12 Jul 2020, Pléiades 1A 18 Jun 2018), which shows Airbus images Rome often but is not a stereo set | 55 that a set exists |
| Older stereo | A GeoEye-1 stereo pair over Rome from about 2009 was used by Sapienza researchers; their surface model of the dense centre was only 8–10 m accurate | 70 that it is still sold |
| Delivery | Archive stereo with the sensor geometry needed for 3D is sold "on request" through sales staff, not by card checkout. A weekend order is unlikely to arrive before Monday | 75 |
| **Licence** | Airbus' licence says a surface model derived from the imagery is never a freely usable derivative; Vantor/Maxar excludes surface models, point clouds and 3D building models too. A model made from bought stereo **cannot go in an open repository** | 85 |
| List prices if you still want it (Apollo, July 2025, 25 km² minimum) | Pléiades stereo $625; Pléiades tri-stereo $937.50; Pléiades Neo stereo $1,062.50; Pléiades Neo tri-stereo $1,375; GeoEye-1 / WorldView 50 cm stereo from $500 | list prices |

**Recommendation: do not buy.** The licence clashes with the open-data rule and delivery would miss the event.

**Free alternative found: national LiDAR (MASE).** A 1 m surface model, licence CC BY 4.0, flown 2008–2011, covers about a third of the central box (roughly 16 km²) along the Tiber: Pantheon area, Campo Marzio, Trastevere, the Ghetto, Aventine, Testaccio. It does not cover the Colosseum, Termini or Esquilino. Download from the ministry's "Download Banca Dati PST" app at https://sim.mase.gov.it/portalediaccesso/mappe/#/viewer/new, which also has the bare-earth model. The portal added coverage on 10 Nov 2026; whether the eastern centre is now included was not checked (C=40).

So G2 becomes: **LoD2 roofs from the free LiDAR where it exists**, LoD1 elsewhere. The age of the survey (2008–2011) must be shown; in the historic centre roofs change little (C=70 [inf]).

How to check for stereo yourself later, if the PA wants to fund it: at https://eocat.esa.int (no login) pick the Pléiades and WorldView ESA archive collections and draw the box; look for 2–3 scenes on the same date, seconds apart, with different incidence angles.

---

## 7. Data layers and their providers

Real layers below were tested live on 13 Nov 2026 unless marked. Endpoints are in the companion inventory.

| Layer | Provider today | Kind | PA swap later |
|---|---|---|---|
| Buildings, roads, POIs | Overture + OSM | open | Roma Capitale cartography (Atlante) |
| PRG, Carta per la Qualità, Rete Ecologica, UNESCO | Roma Capitale GeoServer (WFS/WMS) | open | same |
| Landscape plan (PTPR), Natura 2000 | Regione Lazio GeoServer | open | same |
| Landscape constraints art. 136/142 | MiC SITAP WFS | open | same |
| Schools, nidi, hospitals | Roma Capitale GeoServer | open | same |
| Care homes (RSA), playgrounds | OSM (no official layer found) | open, incomplete | PA registers |
| Public transport live | Roma Mobilità GTFS-RT (positions, delays, alerts) | open | same |
| Road traffic flow | **Simulated loop stations** | simulated | Roma Mobilità loops (93 stations) |
| Road speed samples | Bus probes from GTFS-RT; TomTom/HERE free tiers | open / key | PA floating-car data |
| Air quality | EEA hourly stations (13 Rome NO2 points), Open-Meteo/CAMS model, Sensor.Community | open | ARPA Lazio live feed |
| Rain | Civil Protection radar (5 min) | open | same |
| Shared scooters | Bird GBFS | open | all operators via PA |
| Activity proxy | DigitRoma Wi-Fi sessions (daily CSV) | open | PA crowd sensors |
| Antenna sites | **Simulated register** seeded from OpenCelliD + OSM | simulated (seeded by crowd data) | Authorisation applications (Model A), ARPA opinions |
| EMF baseline field | **cartoradio.it** national grid (MIMIT/FUB): estimated field on 100 m cells, built from the operators' register, one GeoTIFF of about 176 MB dated 8 Sep 2026 | restricted (consent pending) | same, under the consent Roma Capitale obtains |
| EMF measurements | **Simulated monitoring points** + the one ARPA station found (PDF graphs) | simulated | ARPA Lazio measurement points |
| Disruption news | Exa monitors (roadworks, strikes, demonstrations), GTFS-RT alerts | open | PA event calendar |
| Video | none (no Rome webcam source permits storing or analysing frames) | closed | PA cameras with edge counting under the Comune's own DPIA |

Personal data: drop the contact fields (`ref-nome`, `ref-cell`, telephone, e-mail) of Roma layer `DIPPC:241_ServiziSanitarieAssistenziali` at ingest. Inspect accident, complaint and Wi-Fi files before storing; keep aggregates only.

---

## 8. Simulated sensors: specification

> **Superseded on 13 Nov 2026:** only `sim_loops` stays simulated. `sim_register` becomes an *estimated* register built from OpenCelliD + OSM, with EIRP fitted to the Cartoradio grid by sensor fusion (azimuth is not fitted: it cannot be observed reliably from a 100 m grid given OpenCelliD position errors, so it stays unknown and sites are modelled as isotropic; the fit is labelled *uncalibrated*, median error about 9 dB, WS3 PR #10); `sim_emf_points` is replaced by real ARPA Lazio measurement points (needs the DTS5887 table; portal returned 502 on 13 Nov) plus the fused field estimate; `sim_applications` is dropped (the officer enters an application live in the demo). See `docs/decisions.md`.

Each simulator is a provider with a fixed seed and a version, so runs are reproducible.

| Simulator | How values are generated | Anchored to reality by |
|---|---|---|
| `sim_loops` (traffic) | Loop stations placed on main arterials from OSM (count configurable; 93 mirrors the real network). Flow, speed, occupancy every 5 minutes = daily profile by road class × live factor + noise | Live factor comes from real bus speeds (GTFS-RT) and TomTom samples on the same corridor. Inside an operating area, values come from SUMO's own induction-loop detectors instead |
| `sim_register` (antenna sites) | OpenCelliD cells clustered into sites + OSM masts. Operator from network code, technology from radio type. Synthetic fields: sector azimuths, mast height above the building (from G0), EIRP per band from a config table, authorisation status, application date | Site positions are crowd-sourced estimates (cell centroids, often 100 m–1 km from the real mast, C=70). Field names follow the application form (Model A) and the national source register so real records map one-to-one |
| `sim_emf_points` (measurements) | Field model value at chosen points × log-normal error | Error spread taken from published model-vs-measurement deviation (median 1.6–3.8 dB in a 2026 IEEE validation). The real ARPA rooftop station is kept as a separate, real point |
| `sim_applications` (permit inbox) | A handful of synthetic new-installation applications at real addresses | Used only to demonstrate the workflow |

Rules [inf, C=85]:

- Simulators never invent a layer that exists openly. They only fill the three gaps the PA confirmed: loops, antenna register, EMF points.
- Parameters that drive results (EIRP table, noise levels, daily profiles) live in versioned config files with a comment on where each number comes from, or "assumption".
- A **Data honesty panel** in the UI lists every layer as REAL, ESTIMATED (crowd-sourced or modelled) or SIMULATED, with its source and last update.

---

## 9. Probabilistic core

Each dynamic quantity is a **belief layer**: per grid cell a mean, a variance and a timestamp.

1. **Prior** from a model (schedule, forecast, physics).
2. **Update** when an observation arrives, weighted by its `sigma`.
3. **Decay**: variance grows while no data arrives, so stale areas visibly lose confidence.
4. **Output**: mean, range, and probability of exceeding a threshold. Thresholds come from a config file with a legal citation and an "as of" date.

| Belief layer | Prior | Observations |
|---|---|---|
| Transit delay | Static timetable | GTFS-RT trip updates |
| Road speed / flow | Free-flow speed by road class | `sim_loops` (later real loops), bus probes, TomTom samples |
| Air quality | Open-Meteo/CAMS | EEA stations, Sensor.Community |
| Rain | Forecast | Civil Protection radar |
| EMF | Cartoradio grid (section 9a); the twin's own field model where a scenario changes the sites | `sim_emf_points` (later ARPA points) |
| Activity | Population grid + POIs | Wi-Fi sessions, scooter density |

Method options:

| Option | What | When to choose |
|---|---|---|
| P1 (default) | Per-cell Bayesian update (Kalman-style) plus kriging / Gaussian process on the residual between observations and prior | Always: simple, explainable, cheap |
| P2 | Spatio-temporal Gaussian process (GPyTorch) per layer | If P1 looks blocky and the GPU is free |
| P3 | Ensemble data assimilation coupled to the simulators | Out of scope now; name it as the roadmap |

Credibility check: leave-one-station-out on the real air-quality stations. If the predicted uncertainty does not match the errors, the layer is labelled "uncalibrated". EMF stays "uncalibrated" until real measurements exist, and says so.

### 9a. Cartoradio as the EMF baseline

Cartoradio is computed from the real operator register, so it is a far better city-wide starting point than a field computed from crowd-sourced site guesses. Its role:

| Use | How | Note |
|---|---|---|
| City-wide baseline layer | Read the grid for Rome, resample to the twin grid, show as "official estimate (MIMIT/FUB)" | It is itself a model, not a measurement, and publishes no uncertainty. The twin adds an explicit uncertainty band (C=60 on the size of that band) |
| What-if "add an antenna" | New total = √(baseline² + new antenna's field²), with the new antenna from the twin's own model | Needs no knowledge of existing sites, so it is the most defensible scenario |
| Calibrating the simulated register | Tune the synthetic EIRP table until the twin's modelled field is statistically consistent with the cartoradio grid | Makes "move" and "remove" scenarios plausible |
| 300 m permit report | Report the cartoradio class at the point next to the twin's own estimate and range | Two independent numbers are more credible than one |

Conditions [inf, C=80]:

- **File inspected on 13 Nov 2026 (header plus one tile over central Rome, nothing stored).** It is a cloud-optimised GeoTIFF of continuous 32-bit values, not colour classes: 13,243 × 17,255 cells, 100 m cells in Web Mercator (EPSG:3857, so about 74 m on the ground at Rome's latitude), no-data −9999. In the tile around the centre the values read as V/m: median 0.62, 90th percentile 2.6, 99th percentile 6.2, maximum exactly 15.0, about 1.4 at Piazza Venezia. The maximum sitting exactly on 15.0 suggests values may be capped at the attention value (C=55), so treat 15 as "15 or more". Because it is cloud-optimised, the twin can read just the Rome window by byte range instead of downloading all 176 MB.
- Cartoradio's published legal notes forbid reproducing or reusing its maps and data. The permission you were given covers building the proposal; the written consent has to come from cartoradio itself (MIMIT / Fondazione Ugo Bordoni, cartoradio@fub.it). Until then: load it at runtime from its public address, keep it out of the repo and out of any published derived dataset, show the credit "Fonte: Cartoradio – MIMIT/FUB", and mark the provider `redistribution: false` in the manifest.
- The map is deliberately aggregated so that single installations and operators are not visible. Do **not** use it to reverse-engineer individual site positions for the public tier. If the PA wants that for the office tier, it is their call and their consent to obtain.

EMF thresholds (config, not code): exposure limit 20 V/m; attention value 15 V/m as a 24-hour average since Legge 214/2023 (C=85). The older 6 V/m figure is outdated. The decree of 30 July 2026 on emission-limit calculation was not read in full (C=70 that it leaves 15 V/m unchanged).

---

## 10. Scenario engine

Scenarios run on an operating area and always return **baseline vs variant** with ranges.

| Scenario | Engine | Inputs: real / simulated | Whole city? |
|---|---|---|---|
| Add or move an antenna | Baseline from cartoradio; the changed antenna from the twin's model (free-space everywhere, Sionna RT ray tracing on the 300 m neighbourhood or district, diffraction on). Returns P5 / P50 / P95 in V/m and the probability of exceeding the threshold | Baseline official estimate; geometry real (G0/G2); new-site parameters entered by the officer; existing-site parameters simulated | Baseline: yes. Ray tracing: district only |
| Antenna visual impact (viewshed on protected skyline) | Line of sight on G0/G2 + terrain | Real geometry | District |
| Population exposure | Field or noise map × census sections | Real aggregates | Yes |
| Road closure / event | SUMO on the district via an existing open SUMO MCP server; buses from GTFS | Network real; demand synthetic, checked against bus speeds | District. Whole city only as a coarse (mesoscopic) run, unverified on this hardware (C=45) |
| Accessibility / 15-minute city | Routing on OSM + GTFS (r5py) | Real | Yes |
| Noise | NoiseModelling (CNOSSOS-EU) fed by SUMO volumes | Roads real, volumes simulated | District |
| Shadow / solar | Sun geometry on G0/G2 | Real geometry, approximate heights | District |
| Air quality, Tiber flood | **Not simulated.** Show the belief layer and official hazard layers (ISPRA IdroGEO) | Real | Yes |

Traffic demand is the weakest input: no open calibrated demand model of Rome exists. The UI states "synthetic demand" on every traffic result, and the same scenario re-runs with real loop counts once `pa_datex` is connected.

---

## 11. Agents, tools, sponsors and guardrails

**Tools (deterministic, strict JSON schemas)**

| Tool | Returns |
|---|---|
| `resolve_place(text)` | Coordinates, municipio, urban zone |
| `context_check(point, radius=300)` | Sensitive sites, PRG component, constraints, Rete Ecologica, Carta per la Qualità, Natura 2000, each with source layer and distance; "layer not available" where applicable |
| `estimate_field(area, variant?)` | P5/P50/P95 field, probability of exceedance, model used, calibration status |
| `query_layer(layer, area, time)` | Belief values with uncertainty and provider kind |
| `run_scenario(kind, area, change)` | Run id, baseline vs variant indicators |
| `legal_lookup(question)` | Exa search restricted to official domains (normattiva, gazzettaufficiale, agid, garanteprivacy, arpalazio, comune.roma), URL + retrieval time |
| `find_dataset(need)` | Exa dataset scout: publisher, licence, format, update cadence |
| `data_status()` | Honesty panel content: real / estimated / simulated per layer |

**Agents**

| Agent | Job |
|---|---|
| Orchestrator | Understands the request, picks the operating area, calls tools, writes the answer |
| Permit-context agent | Runs the Challenge 02 flow and produces the cited report |
| Scenario agent | Asks clarifying questions before running a simulation, then explains the delta |
| Data steward | Uses Exa to watch for new or changed datasets and news alerts; proposes ingests for human approval |
| Verifier | Checks every number in a draft answer against tool outputs; blocks the answer otherwise |

**Sponsor roles**

| Sponsor | Role in the core flow |
|---|---|
| **Lovable** | The whole front end (section 12), with Supabase auth for the citizen / office tiers and edge functions that hold keys and call the tool API. Keep the repo synced from Lovable so its history is visible |
| **Exa** | Three jobs: legal citations in every report, the dataset scout, and news monitors as a "text sensor" feeding the disruptions layer. Hosted MCP server at `mcp.exa.ai/mcp` |
| **ElevenLabs** | Voice agent with one webhook tool (`ask_twin`) that goes through the same orchestrator and guardrails, plus client tools that move the map. Morning briefing per municipio and a citizen line. First sentence discloses that it is an AI |

**Guardrails**

| Guardrail | Implementation |
|---|---|
| Decision support only | The tool never approves or scores an application. Legge 132/2025 art. 14 keeps the official responsible; AgID guidelines of 9 Nov 2026 require human oversight |
| AI disclosure | Chat banner and first voice line (AI Act art. 50, applicable since 2 Aug 2026) |
| No computed numbers from the model | Verifier agent + answer contract: every figure carries a tool run id or a source URL, otherwise the answer is "insufficient data" |
| Distance is context, not a ban | Fixed wording in reports. The Consiglio di Stato struck down Rome's distance ban in 2021 |
| Uncertainty always shown | Range + method + calibration status; SIMULATED badge |
| Role tiers | Citizen tier sees aggregated antenna data; office tier sees technical fields. Enforced in the API and database row-level security, not in the prompt |
| Untrusted web content | Exa results enter as quoted data with provenance; no state-changing tool can run in the same turn |
| Heavy-run limits | Micro-simulation and ray tracing refuse whole-city areas |
| Privacy | Personal fields dropped at ingest; addresses in logs reduced to street level; no video |
| Provenance (replaces Avalanche) | SHA-256 manifest of every dataset snapshot, simulation run and report, committed to git; a "Verify" view re-hashes a report |

---

## 12. Interface (Lovable)

| Screen | Content |
|---|---|
| City view | 3D map of all Rome; layer switcher; area picker (city / municipio / zone / draw); time slider; uncertainty toggle |
| Ask | Chat and voice with the orchestrator; answers show sources and tool trace |
| Permit check | Address or coordinates → 300 m circle, context list, estimated field with range, downloadable cited report |
| Scenario lab | Pick a scenario and an operating area, edit the change, compare baseline vs variant |
| Data honesty | Every layer: real / estimated / simulated, provider, licence, last update, validation metric |
| Admin (office tier) | Provider switch (`simulated` ↔ `pa`), thresholds config, audit log |

---

## 13. Options at each decision point

Overall packages:

| Package | Contents | Data spend |
|---|---|---|
| **A. Open twin** | G0 whole city, all open layers, simulated sensors, belief layers, antenna module, agents, Exa, voice | None |
| **B. A + landmark splats** | Adds G1 | GPU rental only |
| **C. B + true 3D centre** (recommended) | Adds G2: LoD2 roofs from the free LiDAR along the Tiber | None |

Component options (recommended first):

| Decision | Option 1 (recommended) | Option 2 | Option 3 |
|---|---|---|---|
| 3D viewer | MapLibre + PMTiles building extrusion + deck.gl layers for the whole city; separate splat viewer for landmarks | CesiumJS + 3D Tiles for everything, splats via `KHR_gaussian_splatting` (supported since CesiumJS 1.139) | deck.gl only |
| Why | Lightest for a whole city inside a Lovable React app (C=65; Lovable + 3D map integration was not verified) | One scene for mesh + splats, heavier to tile and host | Fewest libraries, weaker 3D |
| Storage | Heavy static layers as GeoParquet / PMTiles files; operational tables and auth in Supabase Postgres + PostGIS | Everything in PostGIS + TimescaleDB | DuckDB files only |
| Backend host | Tool API as FastAPI on Modal (stable public URL for Lovable and the voice webhook); batch jobs on the workstation or Hyperstack | Everything on the workstation behind a tunnel | Supabase edge functions only (no GPU, no SUMO) |
| Agent framework | Plain tool-calling loop with MCP-style tools (frameworks were not compared in the research, C=50) | Claude Agent SDK | LangGraph, as in the CityLLM paper |
| Traffic | Simulated loops city-wide + SUMO per district | Whole-city mesoscopic SUMO | Routing-only what-ifs (no simulation) |
| EMF model | Cartoradio baseline city-wide + twin model for changes (free-space, Sionna RT per district) | Twin model only (free-space or 3GPP UMa city-wide), cartoradio as a comparison | Cartoradio display only, no scenarios |
| Grid | H3 res 9 city-wide, finer per district | Regular 100 m grid (matches cartoradio) | Census sections |
| Splat training | 4060 Ti 8 GB with downscaled images | Hyperstack A6000 48 GB at $0.50/h | Skip G1 |

---

## 14. Project folder

```
urbs-gemina/
  README.md                 what it is, how to run, data honesty statement
  LICENSE                   open-source licence (code) + DATA_LICENSES.md
  docs/
    design-proposal.md      this file
    data-inventory.md       companion report
    guardrails.md           rules + regulation references
  config/
    providers.yaml          active provider per layer
    thresholds.yaml         legal thresholds with citation and as-of date
    emf_params.yaml         EIRP table, noise levels (each marked source or assumption)
    areas.yaml              municipi / urban zones ids
  data/
    manifest.json           source, licence, hash, real|estimated|simulated
    raw/  processed/        (git-ignored; fetched by scripts)
  twin/
    providers/              open/  simulated/  pa/   (one file per provider)
    ingest/                 scheduled pullers, snapshot hashing
    model/                  city model build: lod1, terrain, tiles, splats
    beliefs/                belief layers, kriging/GP, calibration checks
    scenarios/              emf/  traffic/  access/  noise/
    tools/                  deterministic tool functions
    api/                    FastAPI app exposing tools
  agents/
    orchestrator/  permit/  scenario/  steward/  verifier/
    prompts/                system prompts, answer contract
  voice/                    ElevenLabs agent config, webhook
  web/                      Lovable-synced front end
  eval/                     grounding, refusal, injection and tool-accuracy test sets
  tests/                    unit tests for tools and simulators (test-first)
```

---

## 15. Build order with gates

1. **Decide**: package (A / B / C), viewer option, backend host. Create the repo, licences and `manifest.json`.
2. **Static ingest, whole city**: buildings, boundaries, context layers (Roma, Lazio, SITAP), census. Drop personal fields.
   - **Gate A:** every layer loads with a hash. *No-go:* mark the layer "not available" and continue.
3. **City model G0** and tiles; height check against Urban Atlas.
   - **Gate B:** all of Rome renders in the chosen viewer inside the Lovable app. *No-go:* fall back to viewer option 3.
4. **Provider interface** with the open providers and the three simulators; `data_status()`.
   - **Gate C:** switching a layer between two providers in `providers.yaml` changes the data with no code change.
5. **Deterministic tools**: `context_check`, `estimate_field` (prior), `query_layer`.
   - **Gate D:** scripted addresses match a manual GIS check.
6. **Belief layers** with live ingest; calibration check on air quality.
   - **Gate E:** layers update, show uncertainty, and decay when a feed is paused.
7. **Agents + Exa + verifier**; permit-check flow end to end.
   - **Gate F:** a cited report in which every number traces to a tool run. This is the demo-safe core.
8. **Scenario engine**: antenna what-if (prior, then Sionna on a district), then traffic on one district.
   - **Gate G:** baseline vs variant with ranges for one antenna case and one closure case.
9. **Voice agent** on the same tools; **landmark splats (G1)**; **LoD2 from the free LiDAR (G2)**.
10. **Freeze**: honesty panel complete, eval set run, recorded backup of the flow.

---

## 16. Risks

| Risk | Mitigation |
|---|---|
| Simulated data mistaken for real | `synthetic` flag end to end, SIMULATED badge, honesty panel |
| Antenna positions are estimates | Label "indicative, not official"; state the FOIA route to real data |
| Share-alike licences (OSM/Overture ODbL; GTFS-RT, OpenCelliD, Mapillary CC BY-SA) | Publish derived data under compatible licences; attribution manifest (C=70 on how far share-alike reaches) |
| Roma GeoServer states no licence | Credit Roma Capitale; check its legal notes (C=60 that CC BY applies) |
| cartoradio.it legal notes forbid reuse; consent is promised, not yet written | Runtime read only, not in the repo, credited, `redistribution: false`; ask cartoradio@fub.it for written consent; the twin still works on its own model if consent is refused |
| Traffic results over-trusted | "Synthetic demand" label; rerun path with real loops |
| Whole-city viewer too heavy in the browser | Vector tiles with zoom-dependent detail; gate B fallback |
| Legal classification | Decision support only; not legal advice (C=65 that this keeps it out of the AI Act high-risk class) |

---

## 17. How the build is organised (decided 13 Nov 2026)

No scope is cut for time. The build runs as 10 parallel workstreams, one agent thread each, so every element can be brainstormed, validated and inspected on its own. Briefs, file ownership and the shared interfaces are in `docs/workstreams.md`. Shared interfaces change only through the design hub; final choices from each workstream are recorded in `docs/decisions.md`.

## 17b. Open decisions for you

1. Package A, B or C. All three need no data purchase now that the stereo buy is dropped.
2. Viewer: MapLibre-first or Cesium-first.
3. Backend: Modal or workstation behind a tunnel.
4. Which three scenarios to show first. Suggested: antenna what-if, road closure, population exposure.
5. Whether the Roma Capitale contact can at least confirm the **field list** of a real application (Model A) and the loop-station data format, so the simulated schemas match what they would later plug in.

---

## 18. Add-on module: sports facilities (Challenge 04)

**Verdict: worth adding as a second application on the same twin (C=75 [inf]), provided it starts only after the antenna flow passes gate F.** It reuses most of the platform, shows the twin is a platform rather than a single-purpose tool, and gives Exa its strongest job.

**What the challenge asks:** a map of all places to play sport (municipal facilities, school gyms open to the community, private venues), filterable by discipline, type, municipio and accessibility, with a facility page and a way for managers to update disciplines and hours.

**Data checked on 13 Nov 2026**

| Source | What it has | What it lacks |
|---|---|---|
| Roma GeoServer `DIPPC:243_ServiziSportivi` | 270 municipal facilities as points: name, type, address, municipio, concession holder, active flag, concession expiry | Disciplines, hours, accessibility. Looks dated (a sampled concession expired in 2021) |
| Roma open data `d30` "Centri Sportivi Municipali 2018" (CSV, CC BY) | School gyms run as municipal sports centres | 2018 vintage; contents not opened |
| Roma GeoServer `GABSIN:piscine` | 17 pools with opening period and hours | Seasonal list only |
| Roma GeoServer `DIPPC:percorsi_accessibili` | 12 accessible routes | Far too few to describe accessibility city-wide |
| OpenStreetMap (`leisure=sports_centre`, `pitch`, `fitness_centre`, `swimming_pool`, with `sport=*`) | Private venues, often with the discipline | Completeness unknown; query not run today (Overpass unreachable from the research sandbox) |
| School building register (MIM open data) | Which school buildings have a gym | Not verified (C=70 that the gym flag exists) |

The official data gives **where**, but not **what you can play, when, and whether it is accessible**. That gap is what the agents fill.

**How Exa and the twin combine**

| Part | What it does |
|---|---|
| Municipio scout agents (15, one per municipio) | Use Exa to find each municipio's published lists of school gyms and assigned associations, calls for tender and sports pages; return facility candidates with source URLs |
| Facility enrichment agent | For each facility, searches the web and returns structured fields: disciplines, opening hours, manager, official contact, accessibility notes, each with source URL, retrieval date and a confidence |
| Entity matching (deterministic tool) | Merges GeoServer, CSV, OSM and web results into one record per facility by name and distance |
| Twin-derived indicators (deterministic tools) | Public-transport access (stops and lines nearby, travel-time catchment from GTFS), residents and children within reach (census sections), air quality at outdoor facilities (belief layer), accessible-route proximity where data exists |
| Planning scenario | "Sport deserts": urban zones with many residents and no facility for a given discipline within a chosen travel time; what-if "open this school gym to the community" shows the change in coverage |
| Manager update flow | Lovable + Supabase login for a facility manager to confirm or correct disciplines and hours; confirmed fields replace web-derived ones |

Cost check: Exa agent runs are priced at $0.012–$1.00 each by effort. A few hundred to a few thousand facilities at the low or medium levels stays in the tens of dollars (C=70), inside the free or hackathon credit. The practical limit is the rate cap (about 5 agent requests per second), not money.

**Guardrails specific to this module**

- Web-derived fields are labelled "from the web, unverified" until a manager confirms them. No discipline or opening hour is shown without a source link.
- Publish only organisational contacts. Small associations often list a private mobile number or personal e-mail; drop those, as with the `tel*` and `email1` fields of the GeoServer layer unless they are clearly an office contact.
- Do not present nearby antennas or field values on facility pages. It adds nothing useful for choosing a gym and invites misreading.
- Accessibility is "not known" unless a source states it. Never inferred.

**Risks**

| Risk | Mitigation |
|---|---|
| Scope dilution in a 3-minute demo | One story: the same twin answers a permit question and a sports-planning question. Show one facility page and one "sport desert" map, nothing more |
| Stale official registry | Show the vintage; let the scout agents flag facilities that appear closed |
| Wrong web extractions | Confidence threshold, source links, manager confirmation, spot-check a sample by hand and report the error rate |

**Where it lives in the project:** `twin/modules/sports/` (matching, indicators, scenario), `agents/sports_scout/` and `agents/sports_enrich/`, one extra screen "Sport" in the Lovable app. The antenna flow moves to `twin/modules/antennas/` so both are peers on the shared core.

**Gate S (after gate F):** for one municipio, the map shows merged facilities with at least disciplines and a source for most of them, and the coverage map for one discipline. *No-go:* ship the plain facility map from the official layers and OSM, without enrichment.
