"""Tool ``resolve_place``: text -> coordinates, municipio and urban zone."""
from __future__ import annotations

from typing import Any

from twin.tools.area import locate
from twin.tools.envelope import Source, utc_now
from twin.tools.geocode import GAZETTEER_SOURCE, Candidate, gazetteer_lookup, parse_coordinates
from twin.tools.runtime import ToolRuntime

TOOL = "resolve_place"


def resolve_place(runtime: ToolRuntime, text: str) -> dict[str, Any]:
    inputs = {"text": text}
    warnings: list[str] = []
    sources: list[Source] = []
    kinds: dict[str, str] = {}
    candidates: list[Candidate] = []

    coords = parse_coordinates(text)
    if coords is not None:
        candidates = [Candidate(lon=coords[0], lat=coords[1], label="coordinates as given", source="input",
                                precision="exact")]
        kinds["place"] = "real"
    else:
        saved = gazetteer_lookup(text, runtime.settings.places)
        if saved is not None:
            candidates = [saved]
            kinds["place"] = "estimated"
            sources.append(Source(id=GAZETTEER_SOURCE, retrieved_at=utc_now()))
            warnings.append("Coordinates from the saved demo list are approximate.")
        elif runtime.geocoder is not None:
            try:
                candidates = list(runtime.geocoder.search(text))
                kinds["place"] = "real"
                sources.append(Source(id="osm_nominatim", retrieved_at=utc_now(), url=runtime.geocoder.base_url))
            except Exception as error:  # noqa: BLE001 - geocoder down must not crash the tool
                warnings.append(f"Geocoder unavailable ({type(error).__name__}); try coordinates or a saved place.")

    if not candidates:
        warnings.append("Place not found in Rome.")
        return runtime.envelope(TOOL, inputs, {"found": False}, kinds or {"place": "not_available"}, sources,
                                warnings, status="not_available", reason="Place not found in Rome.")

    best = candidates[0]
    where = locate(best.lon, best.lat, runtime.store, runtime.settings)
    for layer in ("municipi", "urban_zones"):
        snapshot = runtime.store.get(layer)
        if snapshot is not None:
            sources.append(snapshot.source())
            kinds[layer] = "real"
        else:
            warnings.append(f"Layer '{layer}' not available: municipio / urban zone not resolved.")
    if len(candidates) > 1:
        warnings.append(f"{len(candidates)} matches; the first is used. Check the alternatives.")
    result = {
        "found": True,
        "lon": round(best.lon, 6),
        "lat": round(best.lat, 6),
        "label": best.label,
        "precision": best.precision,
        "method": best.source,
        "municipio": where["municipio"],
        "urban_zone": where["urban_zone"],
        "alternatives": [{"lon": round(c.lon, 6), "lat": round(c.lat, 6), "label": c.label} for c in candidates[1:]],
    }
    return runtime.envelope(TOOL, inputs, result, kinds, sources, warnings)


_DEFAULT: list[ToolRuntime] = []


def resolve(text: str) -> dict[str, Any]:
    """``resolve_place`` with the default runtime, for other modules (e.g. the sports pipeline).

    Returns the tool envelope; read ``result["lon"]``, ``result["lat"]``, ``result["municipio"]``,
    ``result["urban_zone"]`` when ``status == "ok"``. Nominatim allows one request per second.
    """
    if not _DEFAULT:
        _DEFAULT.append(ToolRuntime.default())
    return resolve_place(_DEFAULT[0], text)
