"""Read config/ingest.yaml: which layers and feeds exist and where they come from."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

DataKind = Literal["real", "estimated", "simulated"]
DATA_KINDS: tuple[str, ...] = ("real", "estimated", "simulated")
PROTOCOLS = ("wfs", "overpass", "osm_extract", "zip_shapefile", "istat_census", "derived",
             "csv_points", "csv_geocoded", "arcgis_features", "arcgis_image")
FEED_METHODS = ("get", "eea_parquet_zip", "dpc_radar")

#: (min_lon, min_lat, max_lon, max_lat) in WGS84
BBox = tuple[float, float, float, float]


class CatalogError(ValueError):
    """config/ingest.yaml is inconsistent."""


@dataclass(frozen=True)
class SourceSpec:
    id: str
    protocol: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class LayerSpec:
    key: str
    source: str
    data_kind: DataKind
    theme: str
    type_name: str | None = None
    selectors: tuple[str, ...] = ()
    filter: dict[str, Any] = field(default_factory=dict)
    drop_fields: tuple[str, ...] = ()
    clip_to_city: bool = False
    notes: str = ""
    #: Protocol-specific settings, e.g. the census population file.
    options: dict[str, Any] = field(default_factory=dict)
    #: Rows to leave out entirely: {column: [values]}.
    exclude: dict[str, list[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedSpec:
    key: str
    source: str
    data_kind: DataKind
    method: str
    url: str
    extension: str
    cadence: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    product_type: str | None = None


@dataclass(frozen=True)
class Catalog:
    privacy_patterns: tuple[str, ...]
    sources: dict[str, SourceSpec]
    layers: dict[str, LayerSpec]
    live_feeds: dict[str, FeedSpec]
    city_bbox: BBox


def _data_kind(where: str, value: object) -> DataKind:
    if value not in DATA_KINDS:
        raise CatalogError(f"{where}: data_kind must be one of {DATA_KINDS}, got {value!r}")
    return cast(DataKind, value)


def parse_catalog(raw: dict[str, Any], city_bbox: BBox) -> Catalog:
    patterns = tuple(str(p) for p in (raw.get("privacy") or {}).get("drop_field_patterns") or [])

    sources: dict[str, SourceSpec] = {}
    for sid, spec in (raw.get("sources") or {}).items():
        protocol = str(spec.get("protocol"))
        if protocol not in PROTOCOLS:
            raise CatalogError(f"source {sid}: unknown protocol {protocol!r}")
        urls = tuple(spec.get("urls") or [spec["url"]])
        sources[sid] = SourceSpec(id=sid, protocol=protocol, urls=urls)

    layers: dict[str, LayerSpec] = {}
    for key, spec in (raw.get("layers") or {}).items():
        source = str(spec.get("source"))
        if source not in sources:
            raise CatalogError(f"layer {key}: unknown source {source!r}")
        layer = LayerSpec(
            key=key,
            source=source,
            data_kind=_data_kind(f"layer {key}", spec.get("data_kind")),
            theme=str(spec.get("theme", "")),
            type_name=spec.get("type_name"),
            selectors=tuple(spec.get("selectors") or ()),
            filter=dict(spec.get("filter") or {}),
            drop_fields=tuple(spec.get("drop_fields") or ()),
            clip_to_city=bool(spec.get("clip_to_city", False)),
            notes=str(spec.get("notes", "")),
            options=dict(spec.get("options") or {}),
            exclude={str(k): list(v) for k, v in (spec.get("exclude") or {}).items()},
        )
        protocol = sources[source].protocol
        if protocol == "wfs" and not layer.type_name:
            raise CatalogError(f"layer {key}: WFS layers need type_name")
        if protocol in ("overpass", "osm_extract") and not layer.selectors:
            raise CatalogError(f"layer {key}: OSM layers need selectors")
        if protocol in ("csv_points", "csv_geocoded"):
            needed = ["url", "columns"] + (["lat_column", "lon_column"] if protocol == "csv_points"
                                           else ["address_column", "address_source"])
            missing = [name for name in needed if name not in layer.options]
            if missing:
                raise CatalogError(f"layer {key}: {protocol} layers need options {missing}")
        layers[key] = layer

    feeds: dict[str, FeedSpec] = {}
    for key, spec in (raw.get("live_feeds") or {}).items():
        method = str(spec.get("method"))
        if method not in FEED_METHODS:
            raise CatalogError(f"feed {key}: unknown method {method!r}")
        feeds[key] = FeedSpec(
            key=key,
            source=str(spec["source"]),
            data_kind=_data_kind(f"feed {key}", spec.get("data_kind")),
            method=method,
            url=str(spec["url"]),
            extension=str(spec["extension"]),
            cadence=str(spec.get("cadence", "")),
            request=dict(spec.get("request") or {}),
            product_type=spec.get("product_type"),
        )

    return Catalog(privacy_patterns=patterns, sources=sources, layers=layers, live_feeds=feeds,
                   city_bbox=city_bbox)


def load_city_bbox(areas_path: Path) -> BBox:
    areas = yaml.safe_load(areas_path.read_text(encoding="utf-8"))
    west, south, east, north = (float(v) for v in areas["city"]["bbox"])
    return (west, south, east, north)


def load_catalog(path: Path, areas_path: Path | None = None) -> Catalog:
    """Load the catalogue. The city bbox comes from config/areas.yaml next to it."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    bbox = load_city_bbox(areas_path or path.parent / "areas.yaml")
    return parse_catalog(raw, bbox)
