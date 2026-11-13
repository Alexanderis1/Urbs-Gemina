"""Small hand-made inputs for the sports module tests (no real downloads)."""
from __future__ import annotations

import math
from typing import Any

# Near Piazza di Cinecitta, Municipio VII
LON0, LAT0 = 12.5670, 41.8500
M_PER_DEG_LAT = 111_195.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians(LAT0))


def at(east_m: float, north_m: float) -> tuple[float, float]:
    return LON0 + east_m / M_PER_DEG_LON, LAT0 + north_m / M_PER_DEG_LAT


def feature(east_m: float, north_m: float, **props: Any) -> dict[str, Any]:
    lon, lat = at(east_m, north_m)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def geoserver_sports() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": [
        feature(0, 0, fid="243.1", DENOMINAZIONE="Centro Sportivo Fulvio Bernardini", TIPOLOGIA="Calcio",
                MUNICIPIO="VII", INDIRIZZO="Via X 1", CONCESSIONARIO="A.S.D. Bernardini", REF_TEL="3331234567"),
        feature(2000, 0, fid="243.2", DENOMINAZIONE="Piscina Comunale Quadraro", TIPOLOGIA="Piscina",
                MUNICIPIO="VII", CONCESSIONARIO="Mario Rossi"),
        # A second, distinct municipal facility right next to the first one.
        feature(15, 0, fid="243.3", DENOMINAZIONE="Campo Bocce Cinecitta", TIPOLOGIA="Bocce", MUNICIPIO="VII"),
    ]}


def osm_elements() -> dict[str, Any]:
    lon1, lat1 = at(60, 40)
    lon2, lat2 = at(2010, 5)
    lon3, lat3 = at(5000, 5000)
    return {"elements": [
        {"type": "way", "id": 11, "center": {"lon": lon1, "lat": lat1},
         "tags": {"leisure": "sports_centre", "name": "Fulvio Bernardini", "sport": "soccer;tennis",
                  "phone": "+39 06 1234567", "website": "https://bernardini.example"}},
        {"type": "node", "id": 12, "lon": lon2, "lat": lat2,
         "tags": {"leisure": "swimming_pool", "name": "Piscina Quadraro"}},
        {"type": "node", "id": 13, "lon": lon3, "lat": lat3,
         "tags": {"leisure": "fitness_centre", "name": "Gym Private Club", "operator:type": "private"}},
        {"type": "node", "id": 15, "lon": lon3 + 0.01, "lat": lat3,
         "tags": {"leisure": "pitch", "sport": "soccer", "name": "Campo Parrocchia"}},
        {"type": "node", "id": 14, "lon": lon3, "lat": lat3, "tags": {"amenity": "bench"}},
    ]}
