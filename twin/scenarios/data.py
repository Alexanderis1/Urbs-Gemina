"""Inputs a scenario reads, injected by the caller (tool API) so the engine stays testable."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from twin.scenarios.area import AreaLookup


@dataclass(frozen=True)
class FieldSample:
    """Electric field at a point: median in V/m and a log-normal spread in dB."""

    median_v_per_m: float
    sigma_db: float


#: Baseline field at (lon, lat); ``None`` where the source has no data.
FieldFn = Callable[[float, float], Optional[FieldSample]]


@dataclass(frozen=True)
class ScenarioData:
    #: EMF baseline, normally the Cartoradio grid read at runtime (never stored).
    baseline_field: FieldFn | None = None
    #: "real" | "estimated" label of the baseline source. Cartoradio is "estimated" (an official model).
    #: Only traffic loops may be simulated, so a simulated baseline is refused.
    baseline_kind: str = "estimated"
    baseline_source: Mapping[str, Any] | None = None
    #: ISTAT census sections as a GeoJSON FeatureCollection.
    census: Mapping[str, Any] | None = None
    census_source: Mapping[str, Any] | None = None
    #: SUMO road network (.net.xml) covering the operating area, built from OSM.
    road_network: Path | None = None
    road_network_kind: str = "real"
    road_network_source: Mapping[str, Any] | None = None
    #: Real traffic anchors for road closure, keyed by SUMO edge id (matching is the caller's job):
    #: loop-station counts in vehicles per hour, and GTFS-RT bus speeds in m/s.
    loop_counts_veh_per_h: Mapping[str, float] = field(default_factory=dict)
    observed_speeds_m_per_s: Mapping[str, float] = field(default_factory=dict)
    #: Label of the loop counts: "simulated" while sim_loops is the active provider, "real" with pa_datex.
    loop_counts_kind: str = "simulated"
    #: Physical scenarios. Terrain grid (tests, or a pre-loaded DTM); otherwise read from WS2 / WS1 files.
    dtm: Any = None
    #: River lines (GeoJSON FeatureCollection, field 'name'); otherwise rivers_osm.geojson.
    rivers: Mapping[str, Any] | None = None
    #: Live river gauge readings: gauge id -> (level m, sigma m). Real.
    river_levels: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    #: River discharge forecast per gauge: list of (ISO date, m3/s, sigma m3/s). Estimated (GloFAS).
    river_discharge: Mapping[str, Sequence[tuple[str, float, float]]] = field(default_factory=dict)
    #: Wind at the release point: (speed m/s, direction it blows FROM in degrees). Estimated (forecast).
    wind: tuple[float, float] | None = None
    #: Rainfall in mm over the scenario duration as (lon, lat, mm) cells, keyed "radar" (real) or "forecast".
    rain_mm: Mapping[str, Sequence[tuple[float, float, float]]] = field(default_factory=dict)
    #: Boundary lookup for named areas (municipi, urban zones).
    area_lookup: AreaLookup | None = None
    #: Data snapshot hashes (from the manifest) that enter the run id.
    snapshots: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.baseline_kind not in ("real", "estimated"):
            raise ValueError(f"baseline_kind must be 'real' or 'estimated', not {self.baseline_kind!r}")

    def fingerprint(self) -> dict[str, str]:
        """Everything about the data that can change a result, for the run id."""
        out = dict(self.snapshots)
        if "emf_baseline" not in out:
            src = self.baseline_source or {}
            out["emf_baseline"] = f"{src.get('id', 'none' if self.baseline_field is None else 'unnamed')}"
        if "census" not in out:
            out["census"] = ("none" if self.census is None else
                             hashlib.sha256(json.dumps(self.census, sort_keys=True).encode()).hexdigest())
        if self.loop_counts_veh_per_h and "loop_counts" not in out:
            out["loop_counts"] = _json_hash(self.loop_counts_veh_per_h)
        if self.observed_speeds_m_per_s and "observed_speeds" not in out:
            out["observed_speeds"] = _json_hash(self.observed_speeds_m_per_s)
        for key, value in (("rivers", self.rivers), ("river_levels", self.river_levels), ("rain_mm", self.rain_mm),
                           ("river_discharge", self.river_discharge)):
            if value and key not in out:
                out[key] = _json_hash(value)
        if self.wind is not None and "wind" not in out:
            out["wind"] = f"{self.wind[0]:.2f}@{self.wind[1]:.0f}"
        if self.dtm is not None and "dtm" not in out:
            z = getattr(self.dtm, "z", None)
            out["dtm"] = hashlib.sha256(z.tobytes()).hexdigest() if z is not None else "unknown"
        if "road_network" not in out:
            out["road_network"] = ("none" if self.road_network is None else
                                   _file_hash(self.road_network))
        return out


def _json_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(value), sort_keys=True, default=str).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"missing:{path}"
