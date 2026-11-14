# Urbs Gemina

*Rome's open digital twin. Every number shows how sure it is.*

**Live app: https://urbs-gemina.lovable.app** (residents) · staff sign-in at https://urbs-gemina.lovable.app/staff

An open digital twin of the whole city of Rome for the public administration, built at AgenticHack Rome (13-14 November 2026).
It puts a 3D model of every building in Rome, official context layers, live public feeds and physical models behind one interface.
Residents get plain answers about the place they are in. City staff can watch the city, ask questions, check permits and test "what if" scenarios.
It answers **Challenge 02** (mobile-phone antennas) and, as an add-on, **Challenge 04** (sports facilities).

## What you can do with it

### Residents: public service (no account, Italian first, mobile first)

- **Ambiente**: air quality (NO2, PM10, PM2.5, ozone) and electromagnetic field at your position, on a city heatmap, with a range and the legal limit.
- **Trasporti**: traffic now and over the next hours, drawn along the roads, plus bus delays, roadworks, closures and strikes.
- **Sociale**: sports facilities and museums open on a chosen day and time.
- **Segnala**: report an event in progress (traffic, flooding, fire, emergency) with a photo. The device GPS is required, the photo's own position and time are checked, and all photo metadata is removed before upload. "Entra con SPID" is a labelled demo (real SPID needs AgID accreditation).
- **Ask** in Italian or English, by chat or by voice (ElevenLabs citizen line).

### City staff: Sala operativa (sign in at `/staff`)

- **City view**: the 3D city with live layers fused from real sensors and models, places and sensors as 3D markers, time slider and uncertainty toggle.
- **Ask**: chat with Claude agents over deterministic tools, plus ready-made **playbooks** (municipio morning briefing, civil-protection alert, heat plan for the elderly, school and hospital risk check, event planning, industrial accident, air pollution episode, strike day, and more; see `docs/use-cases.md`). Every figure is checked by a verifier against the tool runs before it is shown.
- **Permit check** (Challenge 02): address, 300 m circle, every constraint and sensitive site inside it, a building-aware field estimate with a range, and a downloadable report with sources.
- **Scenario lab**: river flood (Tiber), heavy rain with sewers, heatwave, chemical plume, emergency access, road closure and traffic event, new antenna. Key figures first (residents, children, elderly, sites), footprint on the map.
- **Segnalazioni**: residents' reports merged into candidate events with a confidence and its reasons; an optional Claude photo check and news check on request; a maintenance crew planner.
- **Sport** (Challenge 04): facilities, and residents with no facility within a 15-minute walk, per discipline and municipio.
- **Data**: freshness of every feed and where each number comes from. Office voice agent for spoken briefings.

## Data honesty

Every record and layer is labelled **real**, **estimated** or **simulated** (`data/manifest.json`), and the label reaches the screen.

- **Only the traffic loop sensors are simulated** (placed at the 93 real Roma Capitale traffic sensor sites), because the real counts are not public. Everything else comes from real sources, filled in with physical models and sensor fusion, and is labelled real or estimated.
- The **antenna register is estimated**: OpenCelliD clusters, OSM masts and the official Cartoradio grid, fitted together. Cartoradio is read at runtime and never stored or committed.
- What-if scenarios carry the officer's **hypothetical** inputs and say so.
- Estimates always come with a range. Numbers come from code, never from the language model. Nothing here is an official measurement.
- No personal data: contact fields are dropped at ingest, reports store no name or e-mail, and staff never see who reported.

## How well it works (checked on real data)

| What | Checked against | Result |
|---|---|---|
| Air layers (NO2, PM, ozone) | EEA stations, months held out of the fit | 90% ranges are honest (coverage 87-95%); NO2 error 9.3 µg/m³ |
| Antenna field register | 487,408 Cartoradio cells, 1 in 5 held out | Median error 7.2 dB (free-space start: 9.2 dB) |
| Building-aware field | Sionna ray tracing on the 3D city | Median difference +1.5 dB |
| Permit distances | Independent geodesic measurement | Within 0.4 m on all three cases |
| Tiber flood | 7 historic floods; official PGRA map | Level error 0.5 m; finds 80% of the official T200 zone |
| Rain flood trouble spots | 4,577 real flooding call-outs 2013-2022 | Ranking skill 0.71 on later years, 0.66-0.86 in 4 cloudbursts |
| Heatwave (night minimum) | 17 rooftop stations; 12 Regione Lazio thermometers (other network, other years) | 0.50 °C error on held-out rooftop stations (0.69 °C without the model); 1.83 °C against 2.24 °C on the Lazio thermometers |
| Emergency access | Lazio 118 official times | Good for before/after changes; absolute times too optimistic |

Details, limits and confidence scores: `docs/scenario-validation.md`, `docs/air_fusion_fit.md`, `docs/register_refit.md`, `docs/physics.md`, `docs/permit_accuracy.md`, `docs/heat_check_lazio.md`.

## How it is built

```
Browser (Lovable app: React, MapLibre + deck.gl)
   │  sign-in, roles, reports database and photos: Lovable Cloud
   │  "tools" edge function: adds the office key, blocks staff-only routes
   ▼
Tool API on Modal (FastAPI, scales to zero)
   ├─ deterministic tools (twin/tools), providers (twin/providers), belief layers (twin/beliefs)
   ├─ Claude agents and verifier (agents), Exa news search, ElevenLabs voice webhook (voice)
   └─ heavy scenarios on a Modal worker; antenna ray tracing on a Modal GPU (Sionna RT)
3D buildings and trees: PMTiles on Cloudflare R2
```

- `twin/providers` live and static data sources · `twin/tools` deterministic tools · `twin/beliefs` mean + variance layers · `twin/scenarios` what-if engines · `twin/physics` antenna physics · `twin/modules` antennas and sports · `twin/api` tool API · `agents` prompts and agent code · `voice` ElevenLabs · `web` front end · `eval` test sets · `config` settings and thresholds (each assumption has a `basis:` note) · `deploy` Modal apps · `docs` design and checks.
- Legal thresholds live only in `config/thresholds.yaml`.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,api,agents,beliefs,physics,providers]"
python -m pytest
python -m mypy                     # strict
python scripts/fetch_static_layers.py   # downloads the static context layers

cd web && npm install && npm run dev    # http://localhost:8080, uses the live public API
npm test && npm run typecheck
```

The server is deployed with `deploy/modal_app.py` (see `deploy/README.md`); the front end's settings are in `web/README.md`.

## Documents

- `docs/design-proposal.md`: architecture and build order
- `docs/decisions.md`: every decision taken, with who agreed it
- `docs/data-inventory.md`: every data source, endpoint, licence and price
- `docs/use-cases.md`: the playbooks
- `docs/citizen-reports.md`: the reporting flow and its privacy rules
- `docs/guardrails.md`: rules the agents and the app follow
- `DATA_LICENSES.md`: licence of each data source

## Licence

Code: MIT. Data: see `DATA_LICENSES.md` (building heights from GlobalBuildingAtlas are CC BY-NC 4.0).
