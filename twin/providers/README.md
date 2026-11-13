# Providers (WS3)

Every data source, real or simulated, implements `twin.providers.base.Provider`
(`describe()` and `fetch(bbox, start, end)`). `config/providers.yaml` picks one
provider per layer; `config/provider_settings.yaml` holds how each one behaves,
with a `basis:` note on every assumption.

| Layer | Provider | Data | Entity type and value keys |
|---|---|---|---|
| traffic_flow | `sim_loops` | simulated | `TrafficFlowObserved`: intensity, averageVehicleSpeed, occupancy |
| antenna_register | `sim_register` | simulated (positions estimated from OpenCelliD) | `AntennaSite`: total_eirp_w, antenna_height_agl_m, n_sectors. Full Model A record: `SimRegisterProvider.sites()[i].to_model_a()` |
| antenna_applications | `sim_applications` | simulated | `AntennaApplication`: same keys. Full record: `applications()` |
| emf_measurements | `sim_emf_points` | simulated | `ElectromagneticFieldObserved`: electricField (V/m) |
| emf_baseline | `cartoradio_grid` | estimated, restricted | `EMFEstimate`: electricField (V/m), at_cap (1 = "15 or more") |
| transit | `roma_gtfs_rt` | real | `Vehicle`: speed_kmh, bearing_deg. `PublicTransportDelayObserved`: delay (s) |
| air_quality | `eea_hourly` | real | `AirQualityObserved`: no2 / pm10 / pm25 (µg/m³) |
| rain | `dpc_radar` | real | `WeatherObserved`: precipitation (mm/h) |
| context_layers | `roma_wfs` | real | static GeoJSON, read at ingest |

Every value has a matching `sigma` (one standard deviation). Simulated records
carry `synthetic=True`. `data_status()` in `status.py` gives the honesty panel
rows; `registry.DATA_KIND` gives the real / estimated / simulated label.

## Where simulated sensors sit

- **Loop stations**: 93 vehicle signals run by a central traffic-control system
  (Omnia, Tmacs, Sigma...) on motorway-to-secondary roads, from Roma Capitale's
  `DIPMOB:Semafori` and `DIPPC:grande_viabilita`, spread at least 600 m apart.
  Free speed and peak flow follow the road class. Detector loops are normally
  fitted at centrally controlled junctions (C=65); the exact real stations are
  not public.
- **Antenna sites**: OpenCelliD cells inside Roma Capitale, grouped by base
  station id and merged within 150 m per operator. Cell centroids are 100 m to
  1 km from the real masts (C=70). If an OSM masts file exists, sites within
  200 m snap to the mast.
- **EMF points**: 30-250 m from a simulated site, as in real campaigns near
  installations.

The seeds are committed in `simulated/seed_data/` so runs are reproducible
offline. Rebuild them with `python -m twin.providers.simulated.build_seeds`.

## Going live

Change the provider id in `config/providers.yaml` (e.g. `antenna_register:
pa_register_file`) and set its access in `config/provider_settings.yaml`. No
code changes (Gate C, see `tests/test_ws3_registry_status.py`).

## Reuse by ingest pullers

`open/gtfs_rt.parse_vehicle_positions`, `open/gtfs_rt.parse_trip_delays`,
`open/eea.read_parquet_rows` + `parse_rows`, and `raster.read_cells` are pure
functions over bytes, for stored snapshots.

## Cartoradio

Read at runtime by HTTP byte range (`/vsicurl/`), held in memory, never written
to disk or the repo. Credit "Fonte: Cartoradio - MIMIT/FUB". Written consent
from MIMIT/FUB is pending.
