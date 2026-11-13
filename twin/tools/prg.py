"""PRG "Sistemi e Regole" component at a point, read live from Roma Capitale's WMS.

Roma publishes no WFS for this layer, so it cannot be ingested city-wide; a
GetFeatureInfo point query is the only reliable read (checked 13 Nov 2026).
Returns the PRG component and the NTA articles (with links) at the site.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping

Fetcher = Callable[[str], Any]
_LINK = re.compile(r"href='([^']+)'[^>]*>\s*([^<]+?)\s*<")


def build_url(base_url: str, layer: str, lon: float, lat: float, half_deg: float) -> str:
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo",
        "layers": layer, "query_layers": layer, "srs": "EPSG:4326",
        "bbox": f"{lon - half_deg},{lat - half_deg},{lon + half_deg},{lat + half_deg}",
        "width": "101", "height": "101", "x": "50", "y": "50",
        "feature_count": "20", "info_format": "application/json",
    }
    return base_url + "?" + urllib.parse.urlencode(params)


def _http_json(url: str, timeout_s: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "urbs-gemina/0.1 (open-source hackathon prototype)"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 (fixed https host)
        return json.load(response)


def parse_features(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One entry per PRG component: name and NTA articles [{article, url}]."""
    seen: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        component = str(props.get("COMPONENTE") or "").strip()
        if not component or component in seen:
            continue
        articles = [{"article": text, "url": url}
                    for url, text in _LINK.findall(str(props.get("NORME_TECNICHE_DI_ATTUAZIONE") or ""))]
        seen[component] = {"distance_m": 0.0, "name": component,
                           "properties": {"component": component, "nta_articles": articles,
                                          "feature_id": feature.get("id")}}
    return list(seen.values())


def prg_at(lon: float, lat: float, meta: Mapping[str, Any], fetcher: Fetcher | None = None) -> list[dict[str, Any]]:
    """PRG components within about ``half_deg`` of the point. Raises on network errors."""
    url = build_url(str(meta["url"]), str(meta["layer"]), lon, lat, float(meta.get("half_deg", 0.0002)))
    fetch: Fetcher = fetcher or (lambda u: _http_json(u, float(meta.get("timeout_s", 10))))
    return parse_features(fetch(url))


_CACHE: dict[tuple[float, float, str, int], list[dict[str, Any]]] = {}


def _cached_at(lon: float, lat: float, meta: Mapping[str, Any], fetcher: Fetcher | None) -> list[dict[str, Any]]:
    key = (round(lon, 5), round(lat, 5), str(meta["layer"]), id(fetcher))
    if key not in _CACHE:
        _CACHE[key] = prg_at(lon, lat, meta, fetcher)
    return _CACHE[key]


def sample_points(lon: float, lat: float, radius_m: float, rings: list[float], bearings: int
                  ) -> list[tuple[float, float, float]]:
    """(lon, lat, distance_m): the centre plus ``bearings`` points on each ring (fractions of the radius)."""
    m_lat = 111_195.0
    m_lon = m_lat * math.cos(math.radians(lat))
    out = [(lon, lat, 0.0)]
    for fraction in rings:
        d = radius_m * fraction
        for i in range(bearings):
            angle = 2 * math.pi * i / bearings
            out.append((lon + d * math.sin(angle) / m_lon, lat + d * math.cos(angle) / m_lat, d))
    return out


def prg_around(lon: float, lat: float, radius_m: float, meta: Mapping[str, Any],
               fetcher: Fetcher | None = None) -> list[dict[str, Any]]:
    """Distinct PRG components at sampled points in the circle, nearest sample distance first.

    Sampled, not exhaustive: a component lying only between sample points is missed.
    Raises when every query fails (city server down).
    """
    points = sample_points(lon, lat, radius_m, [float(r) for r in meta.get("sample_rings", [0.5, 1.0])],
                           int(meta.get("sample_bearings", 8)))
    found: dict[str, dict[str, Any]] = {}
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=int(meta.get("parallel", 6))) as pool:
        futures = {pool.submit(_cached_at, plon, plat, meta, fetcher): d for plon, plat, d in points}
        for future, distance in futures.items():
            try:
                hits = future.result()
            except Exception as error:  # noqa: BLE001 - one failed sample must not lose the others
                errors.append(error)
                continue
            for hit in hits:
                name = hit["name"]
                if name not in found or distance < found[name]["distance_m"]:
                    found[name] = {**hit, "distance_m": round(distance, 1)}
    if len(errors) == len(points):
        raise errors[0]
    return sorted(found.values(), key=lambda h: (h["distance_m"], h["name"]))
