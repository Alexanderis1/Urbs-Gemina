"""The ``area`` argument shared by every tool (shared interface 2). One parser for all streams.

``area`` is ``"city"``, ``"municipio:<n>"`` (1-15; Roman numerals accepted),
``"zone:<CODE>"`` (urban-zone code, case-insensitive) or a GeoJSON Polygon /
MultiPolygon (or a Feature holding one) in WGS84.

Heavy tools call :func:`check_heavy_limit` and answer with status ``refused``
when it raises :class:`AreaTooLarge`.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from twin.providers.base import BBox, ROME_BBOX
from twin.tools.context_check import EARTH_RADIUS_M, distance_to_geometry_m
from twin.tools.envelope import Source, ToolError
from twin.tools.layers import LayerSnapshot, LayerStore, first_property, geometry_bbox, iter_positions
from twin.tools.settings import Settings, default_settings, value

AreaKind = Literal["city", "municipio", "zone", "polygon"]
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
         "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}


class AreaTooLarge(ToolError):
    pass


@dataclass(frozen=True)
class Area:
    #: Canonical id: "city", "municipio:<n>", "zone:<CODE>" or "polygon:<12 hex of the geometry's sha256>".
    id: str
    kind: AreaKind
    #: Polygon or MultiPolygon in WGS84 (the bounding box polygon for the whole city).
    geometry: dict[str, Any]
    bbox: BBox
    area_km2: float
    name: str = ""
    #: Boundary layer snapshot the geometry came from, for provenance.
    source: Source | None = None

    def contains(self, lon: float, lat: float) -> bool:
        if not (self.bbox[0] <= lon <= self.bbox[2] and self.bbox[1] <= lat <= self.bbox[3]):
            return False
        return self.kind == "city" or distance_to_geometry_m(lon, lat, self.geometry) == 0.0

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "name": self.name, "bbox": list(self.bbox),
                "area_km2": round(self.area_km2, 3)}


#: Older name, kept for callers written before the hub fixed the signature.
ResolvedArea = Area


def bbox_polygon(bbox: BBox) -> dict[str, Any]:
    w, s, e, n = bbox
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def polygon_id(geometry: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
    return f"polygon:{digest[:12]}"


def polygon_area_km2(geometry: Mapping[str, Any]) -> float:
    """Planar area on a local equirectangular projection; holes subtracted."""
    kind = geometry["type"]
    polygons = [geometry["coordinates"]] if kind == "Polygon" else geometry["coordinates"]
    total = 0.0
    for rings in polygons:
        for index, ring in enumerate(rings):
            lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
            xs = [math.radians(p[0]) * EARTH_RADIUS_M * math.cos(lat0) for p in ring]
            ys = [math.radians(p[1]) * EARTH_RADIUS_M for p in ring]
            twice = sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))
            area = abs(twice) / 2.0
            total += area if index == 0 else -area
    return total / 1e6


def _normalise_id(raw: Any) -> str:
    text = str(raw).strip().upper()
    for prefix in ("MUNICIPIO", "MUN.", "MUN"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    if text in ROMAN:
        return str(ROMAN[text])
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def _find_feature(snapshot: LayerSnapshot, wanted: str, id_fields: list[str]) -> dict[str, Any] | None:
    target = _normalise_id(wanted)
    for feature in snapshot.features:
        props = feature.get("properties") or {}
        for name in id_fields:
            if name in props and props[name] not in (None, "") and _normalise_id(props[name]) == target:
                return feature
    return None


def _validate_polygon(geometry: Mapping[str, Any]) -> dict[str, Any]:
    if geometry.get("type") == "Feature":
        geometry = geometry.get("geometry") or {}
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ToolError("area must be 'city', 'municipio:<id>', 'zone:<id>' or a GeoJSON Polygon/MultiPolygon")
    positions = list(iter_positions(geometry.get("coordinates")))
    if len(positions) < 4:
        raise ToolError("polygon needs at least 4 positions (closed ring)")
    min_lon, min_lat, max_lon, max_lat = ROME_BBOX
    margin = 0.1
    if not all(min_lon - margin <= p[0] <= max_lon + margin and min_lat - margin <= p[1] <= max_lat + margin
               for p in positions):
        raise ToolError("polygon must lie in the Rome area, in WGS84 [lon, lat] order")
    return dict(geometry)


def resolve_area(area: str | Mapping[str, Any] | None, store: LayerStore | None = None,
                 settings: Settings | None = None) -> Area:
    """Parse the shared ``area`` argument. Other workstreams call this with defaults."""
    settings = settings or default_settings()
    store = store or default_store(settings)
    cfg = settings.areas
    if area is None or area == "city":
        city = cfg.get("city", {})
        bbox_list = city.get("bbox", list(ROME_BBOX))
        bbox: BBox = (float(bbox_list[0]), float(bbox_list[1]), float(bbox_list[2]), float(bbox_list[3]))
        return Area(id="city", kind="city", name=str(city.get("name", "Roma Capitale")), geometry=bbox_polygon(bbox),
                    bbox=bbox, area_km2=float(value(cfg.get("city_area_km2", 1287.36))))
    if isinstance(area, Mapping):
        geometry = _validate_polygon(area)
        found = geometry_bbox(geometry)
        assert found is not None
        return Area(id=polygon_id(geometry), kind="polygon", name="drawn polygon", geometry=geometry, bbox=found,
                    area_km2=polygon_area_km2(geometry))
    if isinstance(area, str) and ":" in area:
        prefix, wanted = area.split(":", 1)
        prefix = prefix.strip().lower()
        if prefix in ("municipio", "mun"):
            layer, kind, ids, names = "municipi", "municipio", "municipio_id_fields", "municipio_name_fields"
        elif prefix in ("zone", "urban_zone", "zu"):
            layer, kind, ids, names = "urban_zones", "zone", "urban_zone_id_fields", "urban_zone_name_fields"
        else:
            raise ToolError(f"unknown area prefix '{prefix}'")
        snapshot = store.get(layer)
        if snapshot is None:
            raise ToolError(f"layer '{layer}' is not available yet, so '{area}' cannot be resolved")
        feature = _find_feature(snapshot, wanted, list(cfg.get(ids, [])))
        if feature is None:
            raise ToolError(f"no {kind} with id '{wanted}' in layer '{layer}'")
        geometry = dict(feature["geometry"])
        found = geometry_bbox(geometry)
        assert found is not None
        name = first_property(feature.get("properties") or {}, list(cfg.get(names, []))) or wanted
        return Area(id=f"{kind}:{_normalise_id(wanted)}", kind=kind,  # type: ignore[arg-type]
                    name=str(name), geometry=geometry, bbox=found,
                    area_km2=polygon_area_km2(geometry), source=snapshot.source())
    raise ToolError("area must be 'city', 'municipio:<id>', 'zone:<id>' or a GeoJSON Polygon/MultiPolygon")


_STORES: dict[str, LayerStore] = {}


def default_store(settings: Settings) -> LayerStore:
    key = str(settings.paths.raw)
    if key not in _STORES:
        _STORES[key] = LayerStore(raw_dir=settings.paths.raw, manifest_path=settings.paths.manifest,
                               processed_dir=settings.paths.data / "processed")
    return _STORES[key]


def check_heavy_limit(area: Area, settings: Settings) -> None:
    """Heavy simulations refuse areas above ``heavy_tools_max_area_km2``."""
    limit = float(value(settings.areas.get("heavy_tools_max_area_km2", 40)))
    if area.area_km2 > limit:
        raise AreaTooLarge(f"area '{area.id}' is {area.area_km2:.1f} km2; heavy tools accept at most {limit:g} km2. "
                           "Pick a municipio, an urban zone or draw a smaller polygon.")


def locate(lon: float, lat: float, store: LayerStore, settings: Settings) -> dict[str, Any]:
    """Municipio and urban zone containing a point ("not_available" when the layer is missing)."""
    cfg = settings.areas
    out: dict[str, Any] = {}
    for layer, label, ids, names in (("municipi", "municipio", "municipio_id_fields", "municipio_name_fields"),
                                     ("urban_zones", "urban_zone", "urban_zone_id_fields",
                                      "urban_zone_name_fields")):
        snapshot = store.get(layer)
        if snapshot is None:
            out[label] = {"status": "not_available"}
            continue
        hit = next((f for f in snapshot.near((lon, lat, lon, lat))
                    if distance_to_geometry_m(lon, lat, f["geometry"]) == 0.0), None)
        if hit is None:
            out[label] = {"status": "outside"}
            continue
        props = hit.get("properties") or {}
        raw_id = first_property(props, list(cfg.get(ids, [])))
        out[label] = {"status": "ok", "id": _normalise_id(raw_id) if raw_id is not None else None,
                      "name": first_property(props, list(cfg.get(names, [])))}
    return out
