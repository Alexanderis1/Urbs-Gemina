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
