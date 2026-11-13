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

Method P1 = Gaussian-process (kriging) update of the residual between readings and the current belief. With a tiny correlation length it is exactly the per-cell Kalman update in `cell.update`. Only per-cell variances are kept between updates (diagonal approximation).

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
