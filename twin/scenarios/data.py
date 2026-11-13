"""Inputs a scenario reads, injected by the caller (tool API) so the engine stays testable."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

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
    #: "real" | "estimated" | "simulated" label of the baseline source.
    baseline_kind: str = "estimated"
    baseline_source: Mapping[str, Any] | None = None
    #: ISTAT census sections as a GeoJSON FeatureCollection.
    census: Mapping[str, Any] | None = None
    census_source: Mapping[str, Any] | None = None
    #: SUMO road network (.net.xml) covering the operating area, built from OSM.
    road_network: Path | None = None
    road_network_kind: str = "real"
    road_network_source: Mapping[str, Any] | None = None
    #: Boundary lookup for named areas (municipi, urban zones).
    area_lookup: AreaLookup | None = None
    #: Data snapshot hashes (from the manifest) that enter the run id.
    snapshots: Mapping[str, str] = field(default_factory=dict)

    def fingerprint(self) -> dict[str, str]:
        """Everything about the data that can change a result, for the run id."""
        out = dict(self.snapshots)
        if "emf_baseline" not in out:
            src = self.baseline_source or {}
            out["emf_baseline"] = f"{src.get('id', 'none' if self.baseline_field is None else 'unnamed')}"
        if "census" not in out:
            out["census"] = ("none" if self.census is None else
                             hashlib.sha256(json.dumps(self.census, sort_keys=True).encode()).hexdigest())
        if "road_network" not in out:
            out["road_network"] = ("none" if self.road_network is None else
                                   _file_hash(self.road_network))
        return out


def _file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return f"missing:{path}"
