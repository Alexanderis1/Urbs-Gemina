# Antenna register refit: hold-out comparison

Run 2026-11-13 23:00 UTC on 487408 Cartoradio cells (100 m) and 2179 estimated sites, one cell in five held out (seed 20261113). Error = median |model - Cartoradio| in dB on cells below the 15 V/m cap. Only aggregates are reported: Cartoradio values are runtime-only.

| Model | Exponent | Fit error (dB) | Hold-out error (dB) |
|---|---|---|---|
| v1-like: free space (n=2), orientation-averaged sectors, 20 m height | 2.0 | 7.54 | 7.67 |
| + fitted path-loss exponent | 2.0 | 7.54 | 7.67 |
| + sector directions (azimuth search) | 2.0 | 7.13 | 7.35 |
| + mast heights from LiDAR roofs | 2.0 | 7.01 | 7.24 |

v1 register (free space, isotropic) reported 9.17 dB on its own fit cells.
Mast heights from LiDAR roofs for 290 of 2179 sites; the rest use a 25 m tower.

```json
{
  "cells": 487408,
  "sites": 2179,
  "v1_reported_fit_error_db": 9.17,
  "sites_on_lidar_roofs": 290,
  "rows": [
    {
      "model": "v1-like: free space (n=2), orientation-averaged sectors, 20 m height",
      "exponent": 2.0,
      "train_db": 7.54,
      "holdout_db": 7.67,
      "holdout_cells": 29808
    },
    {
      "model": "+ fitted path-loss exponent",
      "exponent": 2.0,
      "train_db": 7.54,
      "holdout_db": 7.67,
      "holdout_cells": 29808
    },
    {
      "model": "+ sector directions (azimuth search)",
      "exponent": 2.0,
      "train_db": 7.13,
      "holdout_db": 7.35,
      "holdout_cells": 29808
    },
    {
      "model": "+ mast heights from LiDAR roofs",
      "exponent": 2.0,
      "train_db": 7.01,
      "holdout_db": 7.24,
      "holdout_cells": 29808
    }
  ],
  "azimuth_offsets_histogram": [
    205,
    196,
    176,
    183,
    179,
    172,
    174,
    168,
    203,
    173,
    181,
    169
  ]
}
```
