# Providers (WS3)

Every data source, real or simulated, implements `twin.providers.base.Provider`
(`describe()` and `fetch(bbox, start, end)`). `config/providers.yaml` picks one
provider per layer; `config/provider_settings.yaml` holds how each one behaves,
with a `basis:` note on every assumption.

Rule (13 Nov 2026): **only the road loops are simulated.** Every other layer
uses real sensors, or estimates fused from real sources with a physical model.

| Layer | Provider | Data | Entity type and value keys |
|---|---|---|---|
| traffic_flow | `sim_loops` | **simulated** | `TrafficFlowObserved`: intensity, averageVehicleSpeed, occupancy |
| antenna_register | `est_register` | estimated (OpenCelliD + OSM + Cartoradio fit), restricted | `AntennaSite`: effective_eirp_w, position_sigma_m. Full record: `sites()[i].to_model_a()` (unknown fields are `None`) |
| emf_measurements | `arpa_points` | real (ARPA Lazio); "not available" until the table is loaded | `ElectromagneticFieldObserved`: electricField (V/m) |
| emf_baseline | `cartoradio_grid` | estimated, restricted | `EMFEstimate`: electricField (V/m), at_cap (1 = "15 or more") |
| transit | `roma_gtfs_rt` | real | `Vehicle`: speed_kmh, bearing_deg. `PublicTransportDelayObserved`: delay (s) |
| air_quality | `eea_hourly` | real (official stations) | `AirQualityObserved`: no2 / pm10 / pm25 (µg/m³) |
| air_quality_citizen | `sensor_community` | real (low-cost, larger sigma) | `AirQualityObserved`: pm10 / pm25 |
| air_quality_model | `cams_open_meteo` | estimated (CAMS model) | `AirQualityForecast`: no2 / pm10 / pm25 |
| rain | `dpc_radar` | real | `WeatherObserved`: precipitation (mm/h) |
| micromobility | `bird_gbfs` | real | `MicromobilityVehicle`: availableVehicles, rangeKm (weak activity proxy, C=40) |
| activity_wifi | `roma_wifi` | real (Roma Capitale public Wi-Fi sessions, about one day behind) | `CrowdFlowObserved`: peopleCount (sessions active in the hour, a lower bound on people) |
| context_layers | `roma_wfs` | real | static GeoJSON, read at ingest |

Every value has a matching `sigma` (one standard deviation). Simulated records
carry `synthetic=True`. `data_status()` in `status.py` gives the honesty panel
rows; `registry.DATA_KIND` gives the real / estimated / simulated label.

## How sensors are placed and fused

- **Loop stations (simulated)**: 93 vehicle signals run by a central traffic-control
  system (Omnia, Tmacs, Sigma...) on motorway-to-secondary roads, from Roma Capitale's
  `DIPMOB:Semafori` and `DIPPC:grande_viabilita`, spread at least 600 m apart.
  Free speed and peak flow follow the road class (C=65 that loops sit at such junctions).
  Real bus speeds (`Vehicle.speed_kmh`) are the live correction.
- **Estimated register**: OpenCelliD cells inside Roma Capitale, grouped by base station
  and merged within 150 m per operator; moved to an OSM mast within 200 m, else to a
  Cartoradio peak within 300 m; strong peaks with no site become sites with operator
  "unknown". Effective EIRP is a non-negative least-squares fit of the free-space model to
  the Cartoradio grid, with a one-sigma range. `fit_error_db` reports the median model-vs-
  grid misfit (about 9 dB city-wide on 13 Nov: the isotropic model is crude, so the
  register is "uncalibrated"). Computed at runtime, never stored.

- **Wi-Fi hotspots**: the city's daily anonymised session files (dataset `wifi<year>`) give
  start, end and hotspot address. Only counts per hotspot and hour are kept; DOMAIN,
  LOGINCOUNT, traffic and language are dropped at parse. Addresses are matched to the
  hotspot maps of dataset D.192 (`open/seed_data/wifi_sites.json`, about 99.7% of sessions
  matched on 12 Nov 2026).

Seeds are committed (`simulated/seed_data/`, `estimated/seed_data/`) so runs are
reproducible offline. Rebuild them with `python -m twin.providers.build_seeds`.

## Going live

Change the provider id in `config/providers.yaml` (e.g. `antenna_register:
pa_register_file`) and set its access in `config/provider_settings.yaml`. No
code changes (Gate C, see `tests/test_ws3_registry_status.py`).

## Reuse by ingest pullers

`open/gtfs_rt.parse_vehicle_positions`, `open/gtfs_rt.parse_trip_delays`,
`open/eea.read_parquet_rows` + `parse_rows`, `open/sensor_community.parse_readings`,
`open/gbfs.parse_free_vehicles`, `open/roma_wifi.parse_sessions` + `hourly_counts` and `raster.read_cells` are pure functions over
stored snapshots.

## Cartoradio

Read at runtime by HTTP byte range (`/vsicurl/`), held in memory, never written
to disk or the repo. Credit "Fonte: Cartoradio - MIMIT/FUB". Written consent
from MIMIT/FUB is pending.
