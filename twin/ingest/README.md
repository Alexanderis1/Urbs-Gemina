# Ingest (workstream WS1, gate A)

Two jobs: download the **static context layers** of the whole city once, and keep
**hashed snapshots of the live feeds**. Everything is listed in `config/ingest.yaml`.

## Static layers

```
pip install -e .[ingest]
python scripts/fetch_static_layers.py              # every layer
python scripts/fetch_static_layers.py hospitals    # just one
```

For each layer:

1. download in WGS84 (Roma / Lazio / SITAP WFS, Overpass for OSM, ISTAT zip);
2. hash the downloaded bytes (`raw_sha256`);
3. drop personal fields (`privacy.drop_field_patterns` plus the layer's `drop_fields`) **before** anything is written. Raw downloads are never stored;
4. write `data/processed/<layer>.geojson` and `data/processed/<layer>.parquet` (GeoParquet);
5. record the result in `data/manifest.json` under `snapshots.<layer>`.

A manifest snapshot looks like this:

```json
"health_care": {
  "source": "roma_geoserver", "data_kind": "real", "synthetic": false, "theme": "sensitive_sites",
  "status": "ok", "features": 21, "fetched_at": "2026-11-13T19:40:00Z",
  "raw_sha256": "...", "dropped_fields": ["e-mail", "ref-cell", "ref-nome", "telefono", "..."],
  "files": {"geoparquet": {"path": "data/processed/health_care.parquet", "sha256": "..."},
            "geojson":    {"path": "data/processed/health_care.geojson", "sha256": "..."}}
}
```

A layer that fails gets `"status": "not_available"` and an `error`; the run carries on
(gate A no-go rule). Exit code 1 means at least one layer failed.

## Cleaning and quality checks

Every downloaded layer is cleaned before it is written (`clean_geometries` in `static.py`),
and the manifest entry says what was done under `cleaning`:

- features without geometry are dropped (e.g. empty records in the ZTL layer);
- invalid geometries (self-crossing rings) are repaired with `make_valid`, keeping the
  original dimension;
- features entirely outside the city bbox are dropped (regional layers fetched by envelope);
- columns empty in every row are dropped (`keep_columns` are always kept).

A layer whose server announces the wrong CRS sets `options.true_crs`; the native numbers
are then read in that CRS (Roma's `DIPAU:ReteEcologicaLinea` says EPSG:6708 but holds
EPSG:3004 coordinates).

Some Roma GeoServer views fail on WFS 1.0.0 and set `options.wfs_version: "2.0.0"`. The fire
hydrant view breaks its GeoJSON mid-stream (a server exception after 1,952 of 1,963
features), so `fire_hydrants` reads the same WFS as CSV (`roma_geoserver_csv`, lat/lon columns).

`python -m twin.ingest.quality [layer ...]` checks the processed files again and writes
`data/processed/quality_report.json`. Exact duplicate positions that remain are expected
(several schools in one building, geocoded places on the same street, nested flood scenarios).

## Sensitive sites (one merged layer)

`sensitive_sites` (built last, from the files in `data/processed/`) puts every sensitive
place in one layer with `site_id, category, subtype, name, source_layer, provenance, data_kind`.
Categories: health, education, green, critical_infrastructure, hazardous_industry, government.
Official layers come first; an OSM feature within `dedupe_m` metres of an official site of the
same category is treated as the same site. The recipe (inputs, OSM tag rules, label mapping)
is in `config/ingest.yaml` under `layers.sensitive_sites.options`.

Two official registers feed it as tables (`twin/ingest/tables.py`):

- `health_accredited_lazio`: Regione Lazio's accredited private health facilities, which
  come with coordinates (list of 2014, so some may have closed);
- `public_bodies_ipa`: head offices of ministries, constitutional bodies, authorities and
  agencies from IndicePA. IPA gives only addresses, so they are matched **offline** against
  the house numbers in the OSM Lazio extract (no outside geocoder sees the data).
  `geocode_quality` says `address` (exact house number, `data_kind: real`) or `street`
  (centre of the street, `data_kind: estimated`).

Only the columns listed under `columns` are kept, so names of owners and managers,
VAT numbers and e-mails never reach the files. Facility names that contain a person's
name (s.a.s., s.n.c., doctors' practices) are replaced by a generic label.

PTPR (Regione Lazio landscape plan, Tavole A and B plus the PTP 15/12 constraint layers)
is the official landscape source: those layers carry `theme: landscape_ptpr`.

## Health system of Rome

From the Ministry of Health open data (Italian Open Data Licence v2.0):

- `hospital_beds_2023`: every hospital and accredited clinic in Rome with beds on 1 Jan 2023
  (`beds_acute`, `beds_rehab`, `beds_long_term`, `beds_total`), one row per structure;
- `consultori_roma`: family health centres; `pharmacies_roma`: open pharmacies (register
  updated daily; its own coordinates are often wrong, so addresses are geocoded instead);
- `asl_roma`: ASL Roma 1, 2 and 3 as unions of their municipi (official ASL-municipio table),
  with residents, GPs, paediatricians, clinics, out-of-hours points, home care cases, counts of
  the layers above inside each area and simple ratios (`beds_per_1000`, `residents_per_gp`).
  Run it after the three facility layers.

All positions come from the offline OSM address geocoder (`geocode_quality`).

## Flood context (for WS6)

- `flood_hazard_pgra`: ISPRA flood hazard areas, field `hazard` = P3 (20-50 years), P2
  (100-200 years), P1 (rare). Queried from ISPRA's ArcGIS service with the city bbox and
  clipped to it. The areas overlap (P3 is inside P2 and P1).
- `imperviousness_2018`: Copernicus share of sealed soil, written as a Cloud Optimized
  GeoTIFF `data/processed/imperviousness_2018.tif` (EPSG:3035, 20 m, 0-100 %, 255 = no data).
- `road_underpasses_osm` (tunnel or layer < 0 roads) and `rivers_osm` (river, stream,
  canal) are OSM **lines** (`options.lines: true`) with a short fixed schema (`keep_columns`).

## Live feeds

```
python -m twin.ingest.live                               # one pull of every feed
python -m twin.ingest.live gtfs_rt_vehicle_positions --every 60 --count 60
```

Each pull stores the raw bytes at `data/snapshots/<feed>/<UTC time>_<sha12>.<ext>` and
appends one JSON line to `data/snapshots/<feed>/index.jsonl` (time, URL, SHA-256, size).
Identical bytes are not stored twice (`"unchanged": true`). Presigned URL signatures are
never logged. `twin.ingest.live.latest_snapshot(root, feed)` returns the newest record.

Parsing is done by the WS3 providers (`twin.providers.open.gtfs_rt`, `.eea`,
`twin.providers.raster`), which accept a local snapshot path.

Feeds: GTFS-RT vehicle positions, trip updates and alerts (Roma Mobilità), EEA hourly
air quality for Rome (last 48 h, zip of parquet), Civil Protection rain radar (VMI
GeoTIFF), Bird GBFS scooters.

**Scheduling** is a single command, so any scheduler works: Modal cron (recommended,
matches the hosting plan), a Lovable scheduled job, or cron on a workstation.

## Rules kept here

- No personal data: contact fields are dropped at ingest; tests check that names, phones and e-mails never reach the files.
- Every layer and feed carries `data_kind` (real / estimated / simulated) and `synthetic`.
- `data/raw`, `data/processed` and `data/snapshots` are git-ignored; provenance is the hashes in the manifest plus git.
- Cartoradio is never ingested here (runtime read only, WS3).
