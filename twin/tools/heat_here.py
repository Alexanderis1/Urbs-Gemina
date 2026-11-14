"""Citizen heat service: heat risk today at my position and where to cool off at that hour.

Numbers: the hourly weather forecast (Open-Meteo) at the nearest model point gives the day's
apparent temperature (Steadman, as used by the Australian Bureau of Meteorology); the street-level
temperature layer (``air_temperature``: forecast + night heat island) gives each nearby cell's
temperature at the chosen hour, shifted by tree cover and sealed ground (twin/beliefs/microclimate)
when the heat-island term is off (daytime). Building shade and street canyons are not modelled yet.
Indoor places: Roma Capitale climate refuges with their published hours. Levels and distances come
from config (tools.yaml ``citizen.heat``, thresholds.yaml ``heat``), never from a language model.
"""
from __future__ import annotations

import math
import re
import time as clock
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import h3  # type: ignore[import-untyped]
import yaml

from twin.tools import citizen
from twin.tools.context_check import distance_to_geometry_m
from twin.tools.envelope import Source
from twin.tools.opening_hours import ROME, from_italian, is_open
from twin.tools.query_layer import parse_time
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import value

TOOL = "heat_here"
MONTHS_IT = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
             "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
_CLOSED_SPAN = re.compile(r"dal\s+(\d{1,2})\s+(?:(\w+)\s+)?al\s+(\d{1,2})\s+(\w+)\s+(\d{4})", re.IGNORECASE)

Micro = Callable[[Sequence[str], datetime], Mapping[str, float]]


@dataclass(frozen=True)
class Hour:
    time: datetime
    temperature_c: float
    wind_ms: float
    humidity_pct: float

    @property
    def feels_like_c(self) -> float:
        return apparent_temperature(self.temperature_c, self.humidity_pct, self.wind_ms)


def _cfg(rt: ToolRuntime) -> Mapping[str, Any]:
    return dict(rt.settings.tools["citizen"]["heat"])


def apparent_temperature(t_c: float, rh_pct: float, wind_ms: float) -> float:
    """Steadman (1994) apparent temperature without radiation: T + 0.33 e - 0.70 v - 4.00 (e in hPa, v at 10 m)."""
    e = rh_pct / 100.0 * 6.105 * math.exp(17.27 * t_c / (237.7 + t_c))
    return t_c + 0.33 * e - 0.70 * wind_ms - 4.00


def risk_level(rt: ToolRuntime, feels_like_max: float) -> dict[str, Any]:
    cfg = _cfg(rt)
    uppers = [float(value(cfg["caution_c"])), float(value(cfg["risk_c"])),
              float(rt.settings.thresholds["heat"]["hot_day_tmax_c"]["value"])]
    i = citizen.band(feels_like_max, [u - 1e-9 for u in uppers])  # at or above a value = the higher band
    return {"index": i, "label_it": cfg["labels_it"][i - 1]}


def _walk(rt: ToolRuntime, metres_straight: float) -> tuple[int, int]:
    cfg = _cfg(rt)
    street = metres_straight * float(value(cfg["detour_factor"]))
    return round(street), max(1, round(street / (float(value(cfg["walk_speed_kmh"])) * 1000 / 60)))


def _closed_period(text: str, at: datetime) -> bool:
    for match in _CLOSED_SPAN.finditer(text or ""):
        d1, m1, d2, m2, year = match.groups()
        month2 = MONTHS_IT.get(m2.lower())
        month1 = MONTHS_IT.get((m1 or m2).lower())
        if month1 is None or month2 is None:
            continue
        start = datetime(int(year), month1, int(d1), tzinfo=ROME)
        end = datetime(int(year), month2, int(d2), tzinfo=ROME) + timedelta(days=1)
        if start <= at.astimezone(ROME) < end:
            return True
    return False


def indoor_places(rt: ToolRuntime, point: Sequence[float], at: datetime) -> list[dict[str, Any]]:
    """Climate refuges (air-conditioned public places), open first, then nearest."""
    snapshot = rt.store.get("climate_refuges_indoor")
    if snapshot is None:
        return []
    radius = float(value(_cfg(rt)["walk_radius_m"])) * 3  # indoor refuges are worth a longer walk
    lon, lat = float(point[0]), float(point[1])
    out = []
    for feature in snapshot.near((lon - 0.06, lat - 0.05, lon + 0.06, lat + 0.05)):
        props = feature.get("properties") or {}
        metres = distance_to_geometry_m(lon, lat, feature["geometry"])
        if metres > radius:
            continue
        hours = str(props.get("orari") or "")
        closure = str(props.get("chiusura_e") or "")
        if "chius" in hours.lower() or ("chiusa" in closure.lower() and "attualmente" in closure.lower()):
            open_at: bool | None = False
        elif _closed_period(closure, at):
            open_at = False
        else:
            open_at = is_open(from_italian(hours), at)
        street_m, minutes = _walk(rt, metres)
        coords = feature["geometry"].get("coordinates") or [None, None]
        out.append({"name": props.get("nome"), "category": props.get("tipo"), "address": props.get("indirizzo"),
                    "opening_hours": hours or None, "open_at": open_at,
                    "air_conditioned": str(props.get("aria_cond") or "").upper() == "SI",
                    "walk_m": street_m, "walk_min": minutes, "lon": coords[0], "lat": coords[1],
                    "source": "Roma Capitale, rifugi climatici"})
    rank = {True: 0, None: 1, False: 2}
    out.sort(key=lambda p: (rank[p["open_at"]], p["walk_m"]))
    return out[: int(value(_cfg(rt)["max_places"]))]


def _near_count(rt: ToolRuntime, layer: str, lon: float, lat: float, metres: float) -> int:
    snapshot = rt.store.get(layer)
    if snapshot is None:
        return 0
    pad = metres / 80_000
    return sum(1 for f in snapshot.near((lon - pad, lat - pad, lon + pad, lat + pad))
               if distance_to_geometry_m(lon, lat, f["geometry"]) <= metres)


def open_air_spots(rt: ToolRuntime, point: Sequence[float], rows: Mapping[str, Mapping[str, Any]],
                   humidity: float, wind: float, micro: Micro, at: datetime | None = None
                   ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Nearby street-level cells ranked by predicted apparent temperature, then walking time."""
    from twin.beliefs.config import grid_resolution
    cfg = _cfg(rt)
    res = grid_resolution()
    lon, lat = float(point[0]), float(point[1])
    centre = h3.latlng_to_cell(lat, lon, res)
    radius = float(value(cfg["walk_radius_m"]))
    k = max(1, math.ceil(radius / (h3.average_hexagon_edge_length(res, unit="m") * 1.5)))
    cells = [c for c in h3.grid_disk(centre, k) if c in rows]
    shift = micro(cells, at or datetime.now(timezone.utc))
    scored = []
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        metres = distance_to_geometry_m(lon, lat, {"type": "Point", "coordinates": [clon, clat]})
        if metres > radius and cell != centre:
            continue
        row = rows[cell]
        t = float(row.get("p50", 0.0)) + float(shift.get(cell, 0.0))
        half = (float(row.get("p95", t)) - float(row.get("p5", t))) / 2
        feels = apparent_temperature(t, humidity, wind)
        street_m, minutes = _walk(rt, metres)
        scored.append({"cell": cell, "lon": round(clon, 5), "lat": round(clat, 5), "temperature_c": round(t, 1),
                       "feels_like_c": round(feels, 1), "low_c": round(feels - half, 1), "high_c": round(feels + half, 1),
                       "walk_m": street_m, "walk_min": minutes})
    here = next((s for s in scored if s["cell"] == centre), None)
    if here is None:
        return [], {}
    for s in scored:
        s["cooler_by_c"] = round(here["feels_like_c"] - s["feels_like_c"], 1)
    others = sorted((s for s in scored if s["cell"] != centre), key=lambda s: (s["feels_like_c"], s["walk_m"]))
    best = others[: int(value(cfg["max_places"]))]
    for s in best:
        s["park_nearby"] = _near_count(rt, "parks_municipal", s["lon"], s["lat"], float(value(cfg["park_near_m"]))) > 0
        s["fountains_nearby"] = _near_count(rt, "drinking_fountains", s["lon"], s["lat"], float(value(cfg["fountain_near_m"])))
    return best, here


def _microclimate(rt: ToolRuntime) -> Micro:
    """Daytime shift by tree cover and sealed ground (zero at night, when the heat-island term already counts them)."""
    def shift(cells: Sequence[str], at: datetime) -> Mapping[str, float]:
        try:
            from twin.beliefs import microclimate as micro
            processed = rt.settings.paths.data / "processed"
            rasters = [processed / "tree_cover_2018.tif", processed / "imperviousness_2018.tif"]
            if not all(p.exists() for p in rasters):
                return {}
            spec = yaml.safe_load((rt.settings.paths.config / "beliefs.yaml").read_text(encoding="utf-8"))
            weights = spec["layers"]["air_temperature"]["prior_field"]["covariate"]["weight_by_utc_hour"]["value"]
            day = 1.0 - float(weights[at.astimezone(timezone.utc).hour])
            if day <= 0:
                return {}
            s = micro.microclimate_settings()
            tree = micro.raster_mean_per_cell(rasters[0], cells)
            seal = micro.raster_mean_per_cell(rasters[1], cells)
            mean_t = sum(tree.values()) / len(tree) if tree else 0.0
            mean_s = sum(seal.values()) / len(seal) if seal else 0.0
            return {c: day * (float(s["tree_c_per_pct"]) * (tree.get(c, mean_t) - mean_t)
                              + float(s["imperv_c_per_pct"]) * (seal.get(c, mean_s) - mean_s)) for c in cells}
        except Exception:  # noqa: BLE001 - optional refinement; the plain layer is still an answer
            return {}
    return shift


#: (model point, day) -> (monotonic time, observations); Open-Meteo answers 429 when asked too often.
_FORECAST_CACHE: dict[tuple[float, float, str], tuple[float, list[Any]]] = {}


def _forecast(rt: ToolRuntime, point: Sequence[float], day_start: datetime) -> list[Hour]:
    provider = rt.providers.get("weather_forecast")
    if provider is None:
        return []
    lon, lat = float(point[0]), float(point[1])
    key = (round(lon, 1), round(lat, 1), day_start.isoformat())
    ttl = float(value(rt.settings.tools["citizen"]["cache_minutes"])) * 60.0
    hit = _FORECAST_CACHE.get(key)
    if hit is not None and clock.monotonic() - hit[0] < ttl:
        obs = hit[1]
    else:
        try:
            obs = list(provider.fetch((lon - 0.06, lat - 0.06, lon + 0.06, lat + 0.06), day_start,
                                      day_start + timedelta(hours=23)))
        except Exception:  # noqa: BLE001 - the tool answers "not available" instead of failing
            return []
        _FORECAST_CACHE[key] = (clock.monotonic(), obs)
    if not obs:
        return []
    nearest = min({(o.lon, o.lat) for o in obs}, key=lambda p: (p[0] - lon) ** 2 + (p[1] - lat) ** 2)
    series = []
    for o in sorted((o for o in obs if (o.lon, o.lat) == nearest), key=lambda o: o.observed_at):
        if "temperature_c" not in o.values:
            continue
        series.append(Hour(o.observed_at, float(o.values["temperature_c"]), float(o.values.get("wind_speed_ms", 0.0)),
                           float(o.values.get("humidity_pct", 50.0))))
    return series


def heat_here(rt: ToolRuntime, point: Sequence[float], time: str | None = None,
              build: Callable[[ToolRuntime, str, datetime], dict[str, Any]] | None = None,
              micro: Micro | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    asked = parse_time(time) if time else None
    local_day = (asked or now).astimezone(ROME).replace(hour=0, minute=0, second=0, microsecond=0)
    inputs = {"point": list(point), "time": asked.isoformat() if asked else None}
    series = _forecast(rt, point, local_day.astimezone(timezone.utc))
    kinds = {"weather_forecast": "estimated", "air_temperature": "estimated", "climate_refuges_indoor": "real"}
    sources = [Source(id="om_weather_forecast", retrieved_at=now.isoformat(), url="https://open-meteo.com")]
    if not series:
        return rt.envelope(TOOL, inputs, None, {"weather_forecast": "not_available"}, sources,
                           status="not_available", reason="no weather forecast for this position")
    peak = max(series, key=lambda s: s.feels_like_c)
    target = asked or (peak.time if peak.time > now else now.replace(minute=0, second=0, microsecond=0))
    at_target = min(series, key=lambda s: abs((s.time - target).total_seconds()))
    level = risk_level(rt, peak.feels_like_c)
    env, rows = citizen.city_layer(rt, "air_temperature", citizen._slot(rt, target.isoformat()), build)
    warnings = list(env.get("warnings") or [])
    spots, here = open_air_spots(rt, point, rows, at_target.humidity_pct, at_target.wind_ms,
                                 micro or _microclimate(rt), target) if env.get("status") == "ok" else ([], {})
    indoor = indoor_places(rt, point, target)
    when = target.astimezone(ROME).strftime("%H:%M")
    summary = (f"Oggi qui: {level['label_it'].lower()}. Temperatura percepita massima circa "
               f"{peak.feels_like_c:.0f} °C verso le {peak.time.astimezone(ROME).strftime('%H:%M')}.")
    open_indoor = [p for p in indoor if p["open_at"]]
    if level["index"] == 1:
        open_indoor, quiet = [], True
    else:
        quiet = False
    if open_indoor:
        summary += (f" Alle {when} il luogo fresco al chiuso più vicino aperto è {open_indoor[0]['name']} "
                    f"({open_indoor[0]['walk_min']} min a piedi).")
    if spots and spots[0]["cooler_by_c"] >= 0.5 and not quiet:
        summary += (f" All'aperto, il punto più fresco vicino è a {spots[0]['walk_min']} min a piedi "
                    f"(circa {spots[0]['cooler_by_c']:g} °C percepiti in meno).")
    result = {"risk": level, "feels_like_max_c": round(peak.feels_like_c, 1), "peak_time": peak.time.isoformat(),
              "temperature_max_c": round(max(s.temperature_c for s in series), 1),
              "hours": [{"time": s.time.isoformat(), "temperature_c": round(s.temperature_c, 1),
                         "feels_like_c": round(s.feels_like_c, 1)} for s in series],
              "target_time": target.isoformat(), "here": here, "cool_spots_open_air": spots,
              "cool_places_indoor": indoor, "summary_it": summary,
              "note_it": "Previsione meteo e modello della città, non una misura. L'ombra degli edifici non è ancora "
                         "calcolata. In caso di malore chiama il 112."}
    warnings.append("Building shade and street canyons are not modelled yet; open-air spots differ by tree cover, "
                    "sealed ground and the night heat island.")
    sources += [Source(id=str(s["id"]), retrieved_at=str(s.get("retrieved_at") or now.isoformat()))
                for s in env.get("sources") or [] if isinstance(s, Mapping) and s.get("id")]
    return rt.envelope(TOOL, inputs, result, kinds, sources, warnings)
