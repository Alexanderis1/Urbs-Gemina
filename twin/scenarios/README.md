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

`twin.scenarios.baselines.live_data(kind, area, change)` returns a `ScenarioData` with the real Cartoradio baseline (WS3 provider `cartoradio_grid`, read by byte range for just the window the run needs, held in memory only). The tool API should call `engine.run(kind, area, change, data=live_data(kind, area, change))`. Census and boundaries are read from WS1 layers automatically.

## Kinds

Only traffic may be simulated. The EMF baseline (Cartoradio) and the existing antenna register (OpenCelliD + OSM, parameters fitted to Cartoradio) are `estimated`; a simulated baseline is refused.

| Kind | Change | Engine | Heavy |
|---|---|---|---|
| `antenna` | `{"action": "add", "site": {lon, lat, height_m}, "eirp_w" or "band"}`; `"move"` adds `"from": {...}` | Cartoradio baseline + free-space isotropic worst case; powers combined as log-normal sums (Fenton-Wilkinson). P5/P50/P95 and probability of exceeding the attention value and the limit (`config/thresholds.yaml`) | no |
| `population_exposure` | same as `antenna` | Census sections from `census_sections.geojson` (WS1, found in `layers.search_dirs`; fields `sez_id`, `residents`, `children_0_14`). Field at each section centroid; residents and children in sections flagged (probability ≥ 5%) before and after. Aggregates only; `not_available` until the file exists | no |
| `road_closure` | `{"close": {"edges": [...]}}` or `{"close": {"street": "Via del Corso"}}` | SUMO on the district network, synthetic random-trip demand scaled to loop counts where given (`loop_counts_veh_per_h`), baseline checked against GTFS-RT bus speeds (`observed_speeds_m_per_s`), dynamic rerouting, five demand seeds; baseline, variant and paired difference | yes |

All parameters (grid, sigma, demand density, replicates...) are in `config/scenarios.yaml` with a `basis:` note.

## Road network

`twin.scenarios.traffic.build_network(osm_file, out)` builds the district SUMO network from an OSM extract (street names kept). SUMO: `pip install -e .[scenarios]`.

## Planned

Sionna RT ray tracing on a district (GPU), viewshed on the protected skyline, buses from GTFS in SUMO, accessibility (r5py), noise, shadow.
