"""Read OSM features from a downloaded extract (.osm.pbf) instead of Overpass.

Overpass servers time out or reset connections from the cloud sandbox, so the OSM
layers are filtered locally from the openstreetmap.fr Lazio extract. The output has
the same shape as an Overpass ``out center tags`` answer: nodes keep ``lat``/``lon``,
ways get ``center`` = centre of their bounding box (as Overpass does). Relations are
skipped (C=80 that this loses only a few large sports complexes).
"""
from __future__ import annotations

import atexit
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Sequence

from twin.ingest.catalog import BBox
from twin.ingest.http import Fetch, HttpRequest

#: (key, value); value None means "the key exists with any value".
Condition = tuple[str, str | None]
_SELECTOR = re.compile(r'\["([^"]+)"(?:="([^"]*)")?\]')

#: (url, fetcher) -> local file, so several layers share one download per process. The key
#: holds the fetcher itself (not its id), so a new fetcher never reuses another one's file.
_CACHE: dict[tuple[str, Fetch], Path] = {}


def parse_selector(selector: str) -> list[Condition]:
    """'nwr["k"="v"]["k2"]' -> [("k", "v"), ("k2", None)]. Equality and key-exists tests only."""
    conditions = [(m.group(1), m.group(2)) for m in _SELECTOR.finditer(selector)]
    if not conditions:
        raise ValueError(f"unsupported OSM selector {selector!r}")
    return conditions


def _cleanup() -> None:
    for path in _CACHE.values():
        path.unlink(missing_ok=True)


atexit.register(_cleanup)


def extract_file(url: str, fetch: Fetch) -> tuple[Path, bytes | None]:
    """Download the extract once per process. Returns (path, bytes if just downloaded)."""
    key = (url, fetch)
    if key in _CACHE and _CACHE[key].exists():
        return _CACHE[key], None
    data = fetch(HttpRequest(url, timeout_s=900.0))
    suffix = ".osm" if data.lstrip().startswith(b"<") else ".osm.pbf"
    handle, name = tempfile.mkstemp(suffix=suffix, prefix="osm_extract_")
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    _CACHE[key] = Path(name)
    return _CACHE[key], data


def _matches(tags: dict[str, str], selectors: list[list[Condition]]) -> bool:
    return any(all((k in tags) if v is None else tags.get(k) == v for k, v in conditions)
               for conditions in selectors)


def _inside(lon: float, lat: float, bbox: BBox) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def read_elements(path: Path, selectors: Sequence[str], bbox: BBox, lines: bool = False) -> dict[str, Any]:
    """Overpass-style ``{"elements": [...]}`` of nodes and ways matching any selector inside bbox.

    With ``lines=True`` each way also carries its full ``geometry`` (as Overpass ``out geom``),
    so it can be written as a line instead of a centre point.
    """
    import osmium

    parsed = [parse_selector(s) for s in selectors]
    keys = {k for conditions in parsed for k, _ in conditions}
    elements: list[dict[str, Any]] = []

    class Handler(osmium.SimpleHandler):  # type: ignore[misc,unused-ignore]
        def node(self, n: Any) -> None:
            if not any(k in n.tags for k in keys):
                return
            tags = {t.k: t.v for t in n.tags}
            if _matches(tags, parsed) and n.location.valid() and _inside(n.location.lon, n.location.lat, bbox):
                elements.append({"type": "node", "id": int(n.id), "lat": n.location.lat,
                                 "lon": n.location.lon, "tags": tags})

        def way(self, w: Any) -> None:
            if not any(k in w.tags for k in keys):
                return
            tags = {t.k: t.v for t in w.tags}
            if not _matches(tags, parsed):
                return
            points = [(nd.lon, nd.lat) for nd in w.nodes if nd.location.valid()]
            if not points:
                return
            lons, lats = [p[0] for p in points], [p[1] for p in points]
            lon, lat = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
            if _inside(lon, lat, bbox):
                element: dict[str, Any] = {"type": "way", "id": int(w.id),
                                           "center": {"lat": round(lat, 7), "lon": round(lon, 7)}, "tags": tags}
                if lines and len(points) >= 2:
                    element["geometry"] = [{"lat": round(y, 7), "lon": round(x, 7)} for x, y in points]
                elements.append(element)

    Handler().apply_file(str(path), locations=True)
    elements.sort(key=lambda e: (e["type"], e["id"]))
    return {"elements": elements}
