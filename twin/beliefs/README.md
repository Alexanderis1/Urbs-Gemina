# Belief layers (WS5)

For every H3 hexagon of Rome (resolution 9, about 0.11 km²), each dynamic layer keeps:

- a **best guess** (mean),
- **how sure** it is (variance, shown as a P5-P95 range),
- **when** it last heard a reading.

| Step | What happens | Where |
|---|---|---|
| Prior | With no readings, every cell holds the prior from `config/beliefs.yaml` (constant or by hour) | `layer.prior_layer` |
| Update | A reading corrects its own cell most and neighbours less, weight `exp(-distance / correlation_length_km)`, scaled by its `sigma` | `layer.assimilate`, `layer.posterior` |
| Decay | While the feed is silent, each cell drifts back to the prior and its uncertainty grows, time constant `relax_tau_hours` | `layer.BeliefLayer.at`, `cell.relax` |
| Output | Mean, P5/P50/P95, probability above a threshold (threshold passed in by the caller from `config/thresholds.yaml`) | `api.query`, `api.layer_geojson` |
| Honesty check | Leave-one-station-out: hide each station, predict it from the others, check that 90% of hidden readings fall in the 90% range. Otherwise the layer says "uncalibrated" and why | `calibration.leave_one_station_out`, `api.calibrate` |
| Learned settings | Air layers: CAMS bias, spread, reach, local "nugget" share and memory fitted by maximum likelihood on 2026 EEA history, checked on held-out months (`docs/air_fusion_fit.md`) | `learn.py`, `scripts/fit_air_fusion.py` |

Method P1 = Gaussian-process (kriging) update of the residual between readings and the current belief. With a tiny correlation length it is exactly the per-cell Kalman update in `cell.update`. Only per-cell variances are kept between updates (diagonal approximation).

## Real data only, except road loops

Project rule (Alessandro, 13 Nov 2026): only traffic loops may be simulated. Every other layer refuses synthetic readings (`allow_simulated: false`) and is built from real sensors plus models:

| Layer | Starting point | Real readings fused in |
|---|---|---|
| road_speed | hourly city profile | `traffic_flow` (sim_loops, the one simulated input) + real bus speeds from `transit` (`Vehicle.speed_kmh`, +10 km/h error, stopped buses dropped) |
| air_no2 / pm10 / pm25 | CAMS forecast map (`air_quality_model`, interpolated to every cell) | `air_quality`: EEA stations; PM also `air_quality_citizen` (Sensor.Community, larger error) |
| transit_delay | generic prior | `transit`: GTFS-RT trip updates |
| rain | generic prior | `rain`: Civil Protection radar |
| emf | **Cartoradio grid** (`prior_field: emf_baseline`) | `emf_measurements`, real ARPA points only |
| activity (proxy, C=40) | ~1 per cell | `micromobility`: parked Bird scooters counted per cell (empty covered cells count as 0). Not a people count |
| wifi_sessions | 0 | `activity_wifi`: City Wi-Fi sessions per hotspot and hour (real, a lower bound on people, one day behind) |

Starting maps (`prior_field`) use the forecast hour closest to the layer time. Rain starts from the Open-Meteo forecast and the radar corrects it, fading back to the forecast after `relax_tau_hours`. Air layers stretch spreading along the wind axis from `weather_forecast` (up to 2x at 5 m/s, assumption C=65); the wind used is reported in `result.wind`.

Sensor fusion: a layer can list several `sources` (a source can read a related value, e.g. bus speed, with `scale`/`offset`/`extra_sd`/`drop_below`); every reading is weighted by its own `sigma`, so a precise station counts more than a low-cost sensor. `api.layer_payload(name, cells, start, end, providers)` picks the sources from the config and returns `not_available` when none is connected.

Labels: a layer built from any simulated reading is `simulated` and `synthetic=True`; otherwise `estimated`. EMF and activity are always `uncalibrated` until real measurements exist.

## For the tool API (WS4)

```python
from twin.beliefs.api import build_layer, query, layer_geojson
from twin.beliefs.config import grid_resolution
from twin.beliefs.grid import cells_in_polygon

cells = cells_in_polygon(area_geojson, grid_resolution())
layer = build_layer("road_speed", cells, provider, start, end)
payload = query(layer, threshold=None)   # inputs, result, data_kinds, sources, synthetic, warnings, snapshot_hash
```

`snapshot_hash` goes into the `run_id`. The caller adds `run_id` and `tool`.

## Demo (Gate E)

```
pip install -e ".[dev,beliefs]"
python -m twin.beliefs.demo --out data/processed/beliefs_demo
```

Feeds simulated loop stations into the whole-city road-speed layer from 05:00 to 08:00 UTC, then pauses the feed and shows the layer relaxing back to the prior.

## Observation keys expected from providers (WS3)

| Layer | `entity_type` | `values` key |
|---|---|---|
| road_speed | TrafficFlowObserved | averageVehicleSpeed |
| air_no2 / air_pm10 / air_pm25 | AirQualityObserved | no2 / pm10 / pm25 |
| transit_delay | PublicTransportDelayObserved | delay (s) |
| rain | WeatherObserved | precipitation (mm/h) |
| emf | ElectromagneticFieldObserved | electricField (V/m) |
| activity | CrowdFlowObserved | peopleCount |

These live in `config/beliefs.yaml`, so a provider with different names needs only a config change.

## Crowds view

`crowds.crowds(cells, start, end, providers, residents_path=...)` puts the real activity signals side by side per cell, each with its own margin: City Wi-Fi sessions (people, lower bound, a day late), parked scooters (weak proxy), timetable transit supply (planned), and census residents (static, ISTAT 2021, checked: 2.75 million over the city grid). A cell is `busy` when at least 2 live signals are above their own city-wide 75th percentile (`crowds` block in `config/beliefs.yaml`). Signals with no feed are reported as `not_available`, never filled in.

## Combinations that extract new information

| What | How | Where |
|---|---|---|
| People exposed above a threshold | layer x ISTAT 2021 residents and children per cell, by municipio: expected = sum(residents x P(above)); low/high = whole field at P5/P95 | `exposure.exposure` (census via `crowds.census_per_cell`) |
| Sensor health | leave-one-out prediction of each station from its neighbours; flag median abs z > 3 over 3+ moments, worst first, then re-check | `calibration.sensor_health`, `api.check_sensors` |
| Flash-flood watch | rain layer P(> 10 mm/h) x ISPRA/PGRA hazard zones (worst class per cell) x OSM road underpasses; "watch" at 30%, "warning" at 70% | `flood.flood_watch` |
| Heat and vulnerable people | temperature forecast map x census over-65 / over-75 (ISTAT 2021, 640,779 over-65 checked) x health and care sites (hospitals, clinics, care homes, Lazio-accredited facilities from `sensitive_sites`); threshold 32 degC from `heat` in config | `exposure.heat_watch` |
| Values at sensitive sites | any layer read at each school, hospital, care site...: P5/P50/P95 and chance above a threshold, sorted by risk | `sites.site_values` |
