# Permit tool accuracy: independent distance checks

The three hand-measured QGIS checks were replaced by an automated, independent check (the same geometry measured by different software and a different Earth model). A hand measurement in QGIS by an officer is still welcome as a fourth check.

| Case | Tool (m) | Reference (m) | Difference (m) | Reference method | Pass |
|---|---|---|---|---|---|
| school (point) about 180 m north-east of a state school | 180.35 | 180.49 | -0.15 | WGS84 geodesic (pyproj.Geod) | yes |
| hospital (point) about 260 m south-west of a hospital | 262.49 | 262.77 | -0.28 | WGS84 geodesic (pyproj.Geod) | yes |
| UNESCO site boundary (polygon edge), point about 150 m outside | 150.0 | 150.39 | -0.39 | shapely in UTM 33N (EPSG:32633), scale-corrected | yes |

Tolerance: 1 m or 0.5%, whichever is larger. Query points are listed in the JSON below.

```json
[
  {
    "case": "school (point) about 180 m north-east of a state school",
    "point": [
      12.538577,
      41.887403
    ],
    "tool_m": 180.35,
    "reference_m": 180.49,
    "difference_m": -0.15,
    "reference": "WGS84 geodesic (pyproj.Geod)",
    "pass": true
  },
  {
    "case": "hospital (point) about 260 m south-west of a hospital",
    "point": [
      12.417644,
      41.915737
    ],
    "tool_m": 262.49,
    "reference_m": 262.77,
    "difference_m": -0.28,
    "reference": "WGS84 geodesic (pyproj.Geod)",
    "pass": true
  },
  {
    "case": "UNESCO site boundary (polygon edge), point about 150 m outside",
    "point": [
      12.520733,
      41.88916
    ],
    "tool_m": 150.0,
    "reference_m": 150.39,
    "difference_m": -0.39,
    "reference": "shapely in UTM 33N (EPSG:32633), scale-corrected",
    "pass": true
  }
]
```
