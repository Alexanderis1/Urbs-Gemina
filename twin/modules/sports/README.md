# Sports module (Challenge 04)

A map of every place to play sport in Rome, built on the same twin as the antenna flow.
Design: `docs/design-proposal.md` section 18. Settings and their reasons: `config/sports.yaml`.

| File | What it does |
|---|---|
| `sources.py` | Reads each source (GeoServer sports + pools, open data `d30`, school-gym register, OSM) into one shape. Drops personal fields; keeps a concession holder only if it looks like an organisation |
| `matching.py` | Deterministic merge: similar name and close, or same kind and very close. Same-source records never merge. Every link is reported with its reason, distance and similarity |
| `model.py` | Merged facility: every field keeps its status (`official`, `open_data`, `web_unverified`, `manager_confirmed`, `simulated`, `not_known`) and its sources |
| `web_fields.py` | Rules applied to what the Exa agents return (source URL, confidence floor, vocabulary, accessibility only if stated, organisational contacts only) |
| `manager.py` | Manager confirms or corrects a field; confirmed values beat web values; audit record per change |
| `indicators.py` | Transit stops and routes within 400 m; residents and children within reach |
| `deserts.py` | "Sport deserts" coverage per urban zone, and the what-if "open this school gym" |
| `tools.py` | `sports_facilities` and `sport_deserts`, returning the shared tool response envelope |
| `pipeline.py` | `python -m twin.modules.sports.pipeline fetch|build` -> `data/processed/sports/facilities.geojson` + `match_report.json` |

Agents: `agents/sports_scout/` (one run per municipio) and `agents/sports_enrich/` (per facility).
Gate S: on Municipio VII, merged facilities with disciplines and a source for most, plus the coverage map
for one discipline. No-go: ship the plain facility map from official layers and OSM.
