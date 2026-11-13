"""Read vector layers from Roma Capitale's public GeoServer (WFS, no login).

Layers are often stored in a national projection, so WGS84 is always requested.
Personal contact fields are dropped before anything is returned or stored.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

ROMA_WFS = "https://geoportale.comune.roma.it/geoserver/ows"

#: Property-name fragments that may hold personal data (names, phones, e-mails).
PERSONAL_FIELD_HINTS = ("ref-", "ref_", "tel", "cell", "mail", "referente")

FeatureCollection = dict[str, Any]


def build_url(type_name: str, bbox: tuple[float, float, float, float] | None = None,
              max_features: int | None = None, base_url: str = ROMA_WFS) -> str:
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "srsName": "EPSG:4326",
        "outputFormat": "application/json",
    }
    if bbox is not None:
        params["bbox"] = ",".join(f"{v:.6f}" for v in bbox) + ",EPSG:4326"
    if max_features is not None:
        params["maxFeatures"] = str(max_features)
    return base_url + "?" + urllib.parse.urlencode(params)


def drop_personal_fields(collection: FeatureCollection) -> FeatureCollection:
    for feature in collection.get("features", []):
        properties = feature.get("properties") or {}
        feature["properties"] = {
            key: value
            for key, value in properties.items()
            if not any(hint in key.lower() for hint in PERSONAL_FIELD_HINTS)
        }
    return collection


def fetch_layer(type_name: str, bbox: tuple[float, float, float, float] | None = None,
                max_features: int | None = None, timeout_s: float = 60.0) -> FeatureCollection:
    url = build_url(type_name, bbox, max_features)
    with urllib.request.urlopen(url, timeout=timeout_s) as response:  # noqa: S310 (fixed https host)
        collection: FeatureCollection = json.load(response)
    return drop_personal_fields(collection)
