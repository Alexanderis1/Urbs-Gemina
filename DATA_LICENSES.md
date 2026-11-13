# Data licences

The code is MIT. Data is not: each source keeps its own licence. The full list is in `data/manifest.json`.

| Source | Licence | What it means here |
|---|---|---|
| OpenStreetMap, Overture buildings | ODbL | Share-alike: publish derived databases under ODbL, with credit |
| Roma Mobilita GTFS / GTFS-RT, OpenCelliD, Mapillary | CC BY-SA | Share-alike with credit |
| Roma Capitale open data (CKAN) | mostly CC BY | Credit. Do not use the 11 non-commercial datasets |
| Roma Capitale GeoServer | not stated | Credit "Roma Capitale - GeoPortale"; check its legal notes |
| MASE LiDAR, MegaScenes, Open-Meteo, EEA | CC BY 4.0 / open | Credit |
| Cartoradio (MIMIT / Fondazione Ugo Bordoni) | reuse forbidden without consent | Runtime read only. Never commit the file or data derived from it. Written consent pending |

Rules:
- No personal data in the repository or the app. Contact fields are dropped at ingest.
- Simulated data is always flagged `synthetic` and shown with a SIMULATED badge.
- Raw downloads live in `data/raw/` and are git-ignored.
