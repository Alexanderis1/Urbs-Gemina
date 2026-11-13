"""Address -> coordinates: saved demo places first, then OpenStreetMap Nominatim.

Nominatim's usage policy asks for an identifying User-Agent, at most one
request per second and caching; results are cached in memory for the process.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from twin.providers.base import BBox, ROME_BBOX

NOMINATIM_SOURCE = "osm_nominatim"
GAZETTEER_SOURCE = "config_places"

#: "41.896, 12.482" or "12.482 41.896"
_COORDS = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Candidate:
    lon: float
    lat: float
    label: str
    source: str
    precision: str
    url: str | None = None


Fetcher = Callable[[str], Any]


def normalise(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    stripped = re.sub(r"[^a-z0-9 ,']", " ", stripped.lower())
    stripped = re.sub(r"\b(roma|rome|rm|italia|italy)\b", " ", stripped)
    return re.sub(r"[\s,]+", " ", stripped).strip()


def parse_coordinates(text: str, bbox: BBox = ROME_BBOX) -> tuple[float, float] | None:
    """(lon, lat) if the text is a coordinate pair inside or near Rome, in either order."""
    match = _COORDS.match(text)
    if not match:
        return None
    a, b = float(match.group(1)), float(match.group(2))
    min_lon, min_lat, max_lon, max_lat = bbox

    def inside(lon: float, lat: float) -> bool:
        return min_lon - 0.2 <= lon <= max_lon + 0.2 and min_lat - 0.2 <= lat <= max_lat + 0.2

    if inside(b, a):
        return b, a  # "lat, lon": the order used by most map apps
    if inside(a, b):
        return a, b
    return None


def gazetteer_lookup(text: str, places: Mapping[str, Any]) -> Candidate | None:
    wanted = normalise(text)
    for place in places.get("places", []):
        names = [place["name"], *place.get("aliases", [])]
        if any(normalise(name) == wanted for name in names):
            return Candidate(lon=float(place["lon"]), lat=float(place["lat"]), label=str(place["name"]),
                             source=GAZETTEER_SOURCE, precision="approximate")
    return None


def _http_get_json(url: str, user_agent: str, timeout_s: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Language": "it,en"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 (fixed https host)
        return json.load(response)


class Nominatim:
    def __init__(self, base_url: str, user_agent: str, timeout_s: float = 10.0, max_results: int = 3,
                 bbox: BBox = ROME_BBOX, fetcher: Fetcher | None = None) -> None:
        self.base_url = base_url
        self.max_results = max_results
        self.bbox = bbox
        self._fetch: Fetcher = fetcher or (lambda url: _http_get_json(url, user_agent, timeout_s))
        self._cache: dict[str, tuple[Candidate, ...]] = {}

    def url_for(self, text: str) -> str:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        params = {
            "q": text,
            "format": "jsonv2",
            "limit": str(self.max_results),
            "countrycodes": "it",
            "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}",
            "bounded": "1",
        }
        return self.base_url + "?" + urllib.parse.urlencode(params)

    def _search(self, text: str) -> tuple[Candidate, ...]:
        url = self.url_for(text)
        rows = self._fetch(url) or []
        return tuple(
            Candidate(lon=float(row["lon"]), lat=float(row["lat"]), label=str(row.get("display_name", text)),
                      source=NOMINATIM_SOURCE, precision=str(row.get("addresstype") or row.get("type") or "unknown"),
                      url=self.base_url)
            for row in rows
        )

    def search(self, text: str) -> tuple[Candidate, ...]:
        key = text.strip().lower()
        if key not in self._cache:
            self._cache[key] = self._search(text)
        return self._cache[key]
