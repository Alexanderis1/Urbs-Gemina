"""Merge official and OSM layers into one layer of sensitive sites.

Every row has a ``category`` (health, education, green, critical_infrastructure,
hazardous_industry, government), a ``subtype``, a ``name``, the ``source_layer`` it
came from and its ``provenance`` (official or osm). Inputs are taken in the order of
config/ingest.yaml (official first). A feature within ``dedupe_m`` metres of a site
already kept in the same category is treated as the same site and dropped, so OSM only
fills gaps. Personal fields were already removed when each input layer was ingested,
and only the columns below are kept.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from twin.ingest.catalog import LayerSpec

OUTPUT_COLUMNS = ["site_id", "category", "subtype", "name", "source_layer", "provenance", "data_kind"]
METRIC_CRS = "EPSG:32633"  # UTM 33N covers Rome; distances in metres


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd  # type: ignore[import-untyped,import-not-found,unused-ignore]

        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _osm_type(row: Any, rules: list[dict[str, Any]]) -> tuple[str, str] | None:
    for rule in rules:
        if _text(row.get(rule["tag"])) == str(rule["value"]):
            return str(rule["category"]), str(rule["subtype"])
    return None


def _rows(spec: dict[str, Any], frame: Any, rules: list[dict[str, Any]],
          subtype_map: dict[str, str]) -> list[dict[str, Any]]:
    layer = str(spec["layer"])
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        if spec.get("osm_rules"):
            typed = _osm_type(row, rules)
            if typed is None:
                continue
            category, subtype = typed
        else:
            category = str(spec["category"])
            field = spec.get("subtype_field")
            subtype = _text(row.get(field)) if field else str(spec["subtype"])
            subtype = subtype_map.get(subtype, subtype) or "unspecified"
        id_field = str(spec.get("id", ""))
        ident = ((_text(row.get(id_field)) if id_field else "") or _text(row.get("osm_id"))
                 or _text(row.get("feature_id")) or str(index))
        rows.append({
            "site_id": f"{layer}:{ident}",
            "category": category,
            "subtype": subtype,
            "name": _text(row.get(str(spec.get("name", "name")))),
            "source_layer": layer,
            "provenance": str(spec.get("provenance", "official")),
            # Geocoded registers say per row whether the position is exact (real) or estimated.
            "data_kind": (_text(row.get(str(spec["data_kind_field"]))) if spec.get("data_kind_field") else "") or "real",
            "geometry": row.geometry,
        })
    return rows


def build_sensitive_sites(layer: LayerSpec, processed: Path) -> tuple[Any, dict[str, Any]]:
    """Return (GeoDataFrame in EPSG:4326, report with counts, drops and missing inputs)."""
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]
    from shapely import STRtree  # type: ignore[import-untyped,import-not-found,unused-ignore]
    from shapely.geometry import Point  # type: ignore[import-untyped,import-not-found,unused-ignore]

    options = layer.options
    rules: list[dict[str, Any]] = list(options.get("osm_rules") or [])
    subtype_map = {str(k): str(v) for k, v in (options.get("subtype_map") or {}).items()}
    radii: dict[str, float] = {str(k): float(v) for k, v in (options.get("dedupe_m") or {}).items()}
    default_radius = radii.get("default", 50.0)

    kept: list[dict[str, Any]] = []
    kept_points: dict[str, list[tuple[float, float]]] = {}
    missing: list[str] = []
    no_geometry = 0
    duplicates = 0

    for spec in options.get("inputs") or []:
        path = processed / f"{spec['layer']}.parquet"
        if not path.exists():
            missing.append(str(spec["layer"]))
            continue
        frame = gpd.read_parquet(path)
        has_geometry = frame.geometry.notna() & ~frame.geometry.is_empty
        no_geometry += int((~has_geometry).sum())
        frame = frame[has_geometry]
        rows = _rows(spec, frame, rules, subtype_map)
        if not rows:
            continue
        points = gpd.GeoSeries([r["geometry"] for r in rows], crs="EPSG:4326").to_crs(METRIC_CRS)
        points = points.representative_point()
        # Compare only with sites kept from earlier inputs, so one layer never dedupes itself.
        trees = {category: STRtree([Point(x, y) for x, y in xy]) for category, xy in kept_points.items() if xy}
        for row, point in zip(rows, points):
            category = row["category"]
            radius = radii.get(category, default_radius)
            tree = trees.get(category)
            if tree is not None and len(tree.query(point, predicate="dwithin", distance=radius)) > 0:
                duplicates += 1
                continue
            kept.append(row)
            kept_points.setdefault(category, []).append((point.x, point.y))

    columns = [*OUTPUT_COLUMNS, "geometry"]
    if kept:
        frame = gpd.GeoDataFrame(kept, geometry="geometry", crs="EPSG:4326")[columns]
    else:
        frame = gpd.GeoDataFrame({c: [] for c in columns}, geometry="geometry", crs="EPSG:4326")
    report = {
        "counts_by_category": dict(sorted(Counter(frame["category"]).items())),
        "counts_by_provenance": dict(sorted(Counter(frame["provenance"]).items())),
        "dropped_duplicates": duplicates,
        "dropped_no_geometry": no_geometry,
        "missing_inputs": missing,
    }
    return frame, report
