# Use cases (playbooks)

A use case is a fixed recipe of tool calls for a common request. Code runs the recipe, Claude writes one
short note from the results, and the verifier checks every figure before anyone sees it. The recipes are
in `config/use_cases.yaml`, the note templates in `agents/prompts/use_cases/`, the runner in
`agents/use_cases.py`.

| Id | For | Needs | What runs |
|---|---|---|---|
| `municipio_briefing` | Officer, every morning | area | transit, traffic (simulated loops), air, rain and temperature forecast, river forecast, disruption news, data status |
| `civil_protection_alert` | Civil protection | area | rain and river forecasts, rain flood with sewers, Tiber at forecast peak, underpasses, PGRA hazard, ambulance reach with flooded roads, official alerts |
| `heat_plan_elderly` | Social services, health | area (+ optional `tmax_c`, `tmin_c`) | heatwave by street with over-65s, tree-planting what-if, care homes, emergency hospitals, pharmacies, parks, official heat plan |
| `site_risk_check` | Schools, hospitals | place | sensitive sites and constraints, PGRA, Seveso zones, underpasses, air, ambulance reach in the district |
| `event_planning` | Events office, police | place (+ `attendees`) | sensitive sites in the perimeter, usual crowd (Wi-Fi), transit, SUMO traffic, ambulance reach with the perimeter closed, hospitals |
| `antenna_permit` | Challenge 02 | place (+ `band`, `height_m`) | context within 300 m, field estimate, residents above thresholds before and after, attention value in the law |
| `sport_deserts` | Challenge 04 | area (+ `discipline`) | facilities and coverage |
| `citizen_area_info` | Residents (public tier) | place | air, forecast, transit, pharmacies, emergency hospitals |
| `industrial_accident` | Civil protection, prefecture | place = plant name (+ `area`, `substance`, `release_kg_s`) | wind forecast, toxic plume with AEGL/IDLH zones, official plan damage zones, hospitals, news, plan rules |
| `air_quality_episode` | Environment, mobility | area | official stations, citizen PM sensors, CAMS model, wind, schools and nurseries, legal limits, traffic-ban notices |
| `strike_day_mobility` | Mobility | area | live transit, transit delay map, road speed map (simulated loops), e-scooters, Wi-Fi crowd proxy, strike notices |

## How to call

- Chat: `POST /ask {"question": "...", "use_case": "heat_plan_elderly", "area": "municipio:5", "params": {"tmax_c": 38}}`.
  For place-based use cases the question text is the place, or send `params.place`.
- List for the interface: `GET /use_cases` (filtered by the caller's tier).
- Voice: `ask_twin` takes optional `use_case` and `place`. The morning briefing is `mode: briefing`.
- Free chat: Claude can call `run_use_case` itself when a request matches.

## Rules kept

- Facts only from tools; a step that cannot run is reported with its reason, never filled in.
- If a figure still cannot be traced after one rewrite, only that line is withheld and the officer is told how many lines were withheld; decision wording blocks the whole note.
- Web text (news, law) stays inside the quote fence; only official domains.
- Agents never approve or decide; "distance is context, not a prohibition".
- Traffic is the only simulated input; officer what-ifs are labelled as hypothetical.

## Checks

- `python -m pytest tests/test_use_cases.py`
- `python -m eval.run_eval --set use_cases` (offline), `--live` (Claude writes the notes; a few cents)
- `python scripts/dry_run_use_cases.py` runs every recipe on the local tool API and real data, no model and no Exa;
  `--model --exa` adds Claude and Exa for one use case.
