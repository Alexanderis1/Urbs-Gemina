# Scenario engine (WS6)

Baseline vs variant on an operating area, always with ranges and a real / estimated / simulated label per input.

## Entry point

```python
from twin.scenarios import engine
from twin.scenarios.data import ScenarioData

envelope = engine.run(kind, area, change, data=ScenarioData(...))
```

- `kind`: see `engine.kinds()`.
- `area`: `"city"`, a named unit (needs `ScenarioData.area_lookup`) or a GeoJSON polygon. Heavy kinds refuse areas above `heavy_tools_max_area_km2` (`config/areas.yaml`).
- Returns the shared tool envelope (`run_id`, `tool="run_scenario"`, `inputs`, `result`, `data_kinds`, `sources`, `synthetic`, `warnings`) plus `cached`. `result.status` is `ok` or `not_available` (with a `reason`).
- `run_id` = SHA-256 of inputs + data fingerprints + hashes of the config files that drive results. Results with status `ok` are cached in `data/cache/scenarios/<run_id>.json` (git-ignored: may contain Cartoradio-derived values).
- Data are injected by the caller (`ScenarioData`): Cartoradio baseline function, census sections, SUMO network, boundary lookup. Missing inputs are reported as `not_available`, never filled in silently.

## Kinds

| Kind | Change | Engine | Heavy |
|---|---|---|---|
| `antenna` | `{"action": "add", "site": {lon, lat, height_m}, "eirp_w" or "band"}`; `"move"` adds `"from": {...}` | Cartoradio baseline + free-space isotropic worst case; powers combined as log-normal sums (Fenton-Wilkinson). P5/P50/P95 and probability of exceeding the attention value and the limit (`config/thresholds.yaml`) | no |
| `population_exposure` | same as `antenna` | Field at each census-section centroid; residents in sections flagged (probability ≥ 5%) before and after. Aggregates only | no |
| `road_closure` | `{"close": {"edges": [...]}}` or `{"close": {"street": "Via del Corso"}}` | SUMO on the district network, synthetic random-trip demand, dynamic rerouting, five demand seeds; baseline, variant and paired difference | yes |

All parameters (grid, sigma, demand density, replicates...) are in `config/scenarios.yaml` with a `basis:` note.

## Road network

`twin.scenarios.traffic.build_network(osm_file, out)` builds the district SUMO network from an OSM extract (street names kept). SUMO: `pip install -e .[scenarios]`.

## Planned

Sionna RT ray tracing on a district (GPU), viewshed on the protected skyline, buses from GTFS in SUMO, accessibility (r5py), noise, shadow.
