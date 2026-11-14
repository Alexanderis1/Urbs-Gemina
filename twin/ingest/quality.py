"""Quality checks for the processed static layers.

For each layer: how many features, how many have no geometry or an invalid one, how many
lie outside the city bbox, how many are exact duplicates, and which columns are always
empty. ``python -m twin.ingest.quality`` prints a table and writes
``data/processed/quality_report.json``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable

from twin.ingest.catalog import BBox, load_catalog

ROOT = Path(__file__).resolve().parents[2]


def check_frame(frame: Any, bbox: BBox) -> dict[str, Any]:
    from shapely.geometry import box  # type: ignore[import-untyped,import-not-found,unused-ignore]

    geometry = frame.geometry
    present = geometry.notna() & ~geometry.is_empty
    valid = geometry[present].is_valid
    city = box(*bbox)
    outside = ~geometry[present].intersects(city)
    duplicates = geometry[present].to_wkb().duplicated()
    columns = [c for c in frame.columns if c != frame.geometry.name]
    empty_columns = [c for c in columns if frame[c].isna().all() or (frame[c].astype(str).str.strip() == "").all()]
    report: dict[str, Any] = {
        "features": int(len(frame)),
        "null_geometries": int((~present).sum()),
        "invalid_geometries": int((~valid).sum()),
        "outside_city": int(outside.sum()),
        "duplicate_geometries": int(duplicates.sum()),
        "empty_columns": empty_columns,
        "crs": str(frame.crs.to_string()) if frame.crs is not None else None,
    }
    issues = []
    if report["features"] == 0:
        issues.append("no features")
    for key, text in (("null_geometries", "without geometry"), ("invalid_geometries", "with invalid geometry"),
                      ("outside_city", "outside the city bbox"), ("duplicate_geometries", "exact duplicates")):
        if report[key]:
            issues.append(f"{report[key]} features {text}")
    if empty_columns:
        issues.append(f"always-empty columns: {', '.join(empty_columns)}")
    if report["crs"] not in (None, "EPSG:4326"):
        issues.append(f"CRS is {report['crs']}, expected EPSG:4326")
    report["issues"] = issues
    return report


def check_layers(processed: Path, keys: Iterable[str], bbox: BBox) -> dict[str, dict[str, Any]]:
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    reports: dict[str, dict[str, Any]] = {}
    for key in keys:
        path = processed / f"{key}.parquet"
        if not path.exists():
            reports[key] = {"issues": ["file missing"]}
            continue
        reports[key] = check_frame(gpd.read_parquet(path), bbox)
    return reports


def main(argv: list[str]) -> int:
    catalog = load_catalog(ROOT / "config" / "ingest.yaml")
    processed = ROOT / "data" / "processed"
    keys = argv or [k for k in catalog.layers if catalog.sources[catalog.layers[k].source].protocol != "arcgis_image"]
    reports = check_layers(processed, keys, catalog.city_bbox)
    (processed / "quality_report.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, report in reports.items():
        status = "ok  " if not report["issues"] else "WARN"
        print(f"{status} {key:32s} {report.get('features', '-'):>7}  {'; '.join(report['issues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
