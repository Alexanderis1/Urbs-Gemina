"""Read config/beliefs.yaml into typed layer specifications."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
ROME_TZ = ZoneInfo("Europe/Rome")


@dataclass(frozen=True)
class PriorSpec:
    """What a cell believes with no readings: a mean (constant or by hour) and a spread."""

    mean: float = 0.0
    sd: float = 1.0
    #: 24 means, hour 0-23 in Rome local time. Overrides ``mean`` when set.
    mean_by_hour: tuple[float, ...] | None = None

    def mean_at(self, at: datetime) -> float:
        if self.mean_by_hour is None:
            return self.mean
        local = at.astimezone(ROME_TZ)
        hour = local.hour + local.minute / 60.0
        # Linear interpolation between hourly values, so the prior has no jumps.
        lo = int(hour) % 24
        hi = (lo + 1) % 24
        frac = hour - int(hour)
        return (1.0 - frac) * self.mean_by_hour[lo] + frac * self.mean_by_hour[hi]

    @property
    def variance(self) -> float:
        return self.sd * self.sd


@dataclass(frozen=True)
class FieldSpec:
    """A gridded real map used as the per-cell starting point (e.g. the Cartoradio grid)."""

    #: Layer name in config/providers.yaml whose provider delivers the map.
    source: str
    entity_types: tuple[str, ...]
    value_key: str


@dataclass(frozen=True)
class LayerSpec:
    name: str
    unit: str
    entity_types: tuple[str, ...]
    value_key: str
    prior: PriorSpec
    correlation_length_km: float
    relax_tau_hours: float
    min_value: float
    #: "loso" (leave-one-station-out check) or "none" (always uncalibrated).
    calibration_method: str
    calibration_note: str
    #: Layer names in config/providers.yaml whose readings feed this layer (sensor fusion).
    sources: tuple[str, ...] = ()
    #: Optional real map that replaces the generic prior cell by cell.
    prior_field: FieldSpec | None = None
    #: Only layers explicitly allowed may use simulated readings (project rule: road loops only).
    allow_simulated: bool = False


def grid_resolution(config_dir: Path = CONFIG_DIR) -> int:
    areas = yaml.safe_load((config_dir / "areas.yaml").read_text(encoding="utf-8"))
    return int(areas["grid"]["city_resolution"])


def _load(config_dir: Path) -> dict[str, Any]:
    raw = yaml.safe_load((config_dir / "beliefs.yaml").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config/beliefs.yaml must be a mapping")
    return raw


def load_specs(config_dir: Path = CONFIG_DIR) -> dict[str, LayerSpec]:
    specs: dict[str, LayerSpec] = {}
    for name, entry in _load(config_dir)["layers"].items():
        prior = entry["prior"]
        by_hour = prior.get("mean_by_hour")
        if by_hour is not None and len(by_hour) != 24:
            raise ValueError(f"{name}: mean_by_hour needs 24 values")
        calibration = entry.get("calibration", {})
        field = entry.get("prior_field")
        specs[str(name)] = LayerSpec(
            name=str(name),
            unit=str(entry["unit"]),
            entity_types=tuple(str(t) for t in entry["entity_types"]),
            value_key=str(entry["value_key"]),
            prior=PriorSpec(
                mean=float(prior.get("mean", 0.0)),
                sd=float(prior["sd"]),
                mean_by_hour=tuple(float(v) for v in by_hour) if by_hour is not None else None,
            ),
            correlation_length_km=float(entry["correlation_length_km"]),
            relax_tau_hours=float(entry["relax_tau_hours"]),
            min_value=float(entry.get("min_value", float("-inf"))),
            calibration_method=str(calibration.get("method", "loso")),
            calibration_note=str(calibration.get("note", "")),
            sources=tuple(str(x) for x in entry.get("sources", [])),
            prior_field=None
            if field is None
            else FieldSpec(
                source=str(field["source"]),
                entity_types=tuple(str(t) for t in field["entity_types"]),
                value_key=str(field["value_key"]),
            ),
            allow_simulated=bool(entry.get("allow_simulated", False)),
        )
    return specs


def load_calibration_rules(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    rules = _load(config_dir)["calibration_rules"]
    if not isinstance(rules, dict):
        raise ValueError("calibration_rules must be a mapping")
    return rules
