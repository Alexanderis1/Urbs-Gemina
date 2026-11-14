# Scenario engine (WS6)

Baseline vs variant on an operating area, always with ranges and a real / estimated / simulated label per input.

## Entry point

```python
from twin.scenarios import engine
from twin.scenarios.data import ScenarioData

envelope = engine.run(kind, area, change, data=ScenarioData(...))
```

- `kind`: see `engine.kinds()`.
- `area`: `"city"`, `"municipio:<1-15>"`, `"zone:<code_zu>"` (boundaries from WS1 layers `municipi.geojson` / `urban_zones.geojson`) or a GeoJSON polygon. Heavy kinds refuse (status `refused`) areas above `heavy_tools_max_area_km2` (`config/areas.yaml`).
- Returns the shared tool envelope (`run_id`, `tool="run_scenario"`, `inputs`, `result`, `data_kinds`, `sources`, `synthetic`, `warnings`) plus top-level `status` (`ok` | `not_available` | `refused`, with `reason` when not ok) and `cached`. A heavy run on a too-large area is `refused`.
- `run_id` = SHA-256 of inputs + data fingerprints + hashes of the config files that drive results. Results with status `ok` are cached in `data/cache/scenarios/<run_id>.json` (git-ignored: may contain Cartoradio-derived values).
- Data are injected by the caller (`ScenarioData`): Cartoradio baseline function, census sections, SUMO network, boundary lookup. Missing inputs are reported as `not_available`, never filled in silently.

## Live inputs

`twin.scenarios.baselines.live_data(kind, area, change)` returns the `ScenarioData` a run needs from live providers: the Cartoradio baseline (antenna, exposure; read by byte range, held in memory only), the GloFAS discharge forecast (river flood, and rain flood with a `river` forecast), rainfall from radar or forecast (rain flood), the wind forecast at the release point (chemical plume, `"wind": "forecast"`), daily max and min temperatures (heatwave). The tool API should call `engine.run(kind, area, change, data=live_data(kind, area, change))`. Static layers (census, boundaries, terrain, outfalls, facilities) are read from the shared processed folder automatically.

With `URBS_SCENARIO_WORKER=modal`, kinds marked `isolate` run on the Modal function `urbs-gemina-scenarios/run_heavy` (`deploy/scenarios_worker.py`, scales to zero).

## Kinds

Only traffic may be simulated. Every other input is real or estimated and labelled in `data_kinds`; every result has P5/P50/P95.

| Kind | Change (examples) | Model | Heavy |
|---|---|---|---|
| `antenna` | `{"action": "add", "site": {lon, lat, height_m}, "eirp_w"}` | Cartoradio baseline + free-space worst case, log-normal power sums; probability over the attention value and limit | no |
| `population_exposure` | same as `antenna` | residents and children in census sections flagged before and after | no |
| `river_flood` | `{"rise_m": 3}`, `{"gauge": "tevere_ripetta", "level_m": 14}`, `{"gauge": ..., "forecast_day": "peak"}` | rating curve, ensemble, height above the river, sea taper, Tiber walls (LiDAR crests); alert-level probabilities; residents, sensitive sites | no (worker) |
| `rain_flood` | `{"rain_mm": 60, "duration_h": 1}`, `{"source": "radar"}`, plus optional `"river": {...}` | fill-and-spill hollows; sewers from Rome's design rules (Comune di Roma 2000) routed on the terrain with surcharge; ACEA outfalls blocked by a high river; hotspots, underpasses | no (worker) |
| `chemical_plume` | `{"site": "Papasped", "substance": "ammonia", "release_kg_s": 5, "wind": {...} or "forecast"}` | Gaussian plume, Briggs urban, wind/stability/release ensemble; AEGL/IDLH zones; official Seveso zones beside | no |
| `emergency_access` | `{"service": "fire", "close": {"street": ...}}`, `"closed_area"`, `"flood": {kind, change}` | shortest times on the OSM road network from real stations; residents beyond the target time before and after | yes |
| `heatwave` | `{"temperature": "forecast"}` or `{"tmax_c": 36, "tmin_c": 24}`, plus `"plant_trees": {"where", "cover_added_pct"}`, `"depave"` | forecast + local effect of sealed ground and tree cover (Copernicus); residents, children, over-65s above heat thresholds; hot map; tree-planting what-if | no |
| `traffic_event` / `road_closure` | `{"close": ...}`, `{"roadworks": ...}`, `{"event": ...}` | SUMO on the district network, demand scaled to loop counts, congestion points | yes |

Static layers added by WS6: `scripts/fetch_heat_layers.py` (tree cover, residents 65+), `scripts/fetch_sewer_layers.py` (ACEA outfalls).

All parameters (grid, sigma, demand density, replicates...) are in `config/scenarios.yaml` with a `basis:` note.

## Road network

`twin.scenarios.traffic.build_network(osm_file, out)` builds the district SUMO network from an OSM extract (street names kept). SUMO: `pip install -e .[scenarios]`.

## Validation

Each model was checked against real events or official figures: see `docs/scenario-validation.md`. Every result has a `calibration` field saying how.

## Planned

Re-fit of the heatwave on the raw ASTI station data (Zenodo 19454855); traffic calibration on real loop counts; Sionna RT ray tracing on a district (GPU), viewshed on the protected skyline, buses from GTFS in SUMO, noise, shadow.
