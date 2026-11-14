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
    #: "bin" = average the map values inside each cell (fine maps like Cartoradio);
    #: "idw" = inverse-distance interpolation to every cell (coarse maps like the CAMS lattice).
    method: str = "bin"
    #: Bias correction learned from real stations (idw maps): start = offset + scale * map.
    offset: float = 0.0
    scale: float = 1.0
    #: Learned error of the corrected map against stations; replaces the map's own sigma when set.
    sd: float | None = None
    #: Optional land-use term (twin/beliefs/landuse.py): start += coef * (covariate(cell) - center).
    covariate_file: str | None = None
    covariate_coef: float = 0.0
    covariate_center: float = 0.0


@dataclass(frozen=True)
class SourceSpec:
    """One real (or allowed simulated) feed of a layer, with how to read it.

    ``entity_types`` / ``value_key`` default to the layer's own. A source that
    measures something related but not identical (bus speed for road speed)
    is converted with ``scale``/``offset`` and gets ``extra_sd`` added to its
    error, so it counts less than a direct measurement.
    """

    layer: str
    entity_types: tuple[str, ...] | None = None
    value_key: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    extra_sd: float = 0.0
    #: Readings below this value are dropped (e.g. a bus standing at a stop).
    drop_below: float | None = None


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
    sources: tuple[SourceSpec, ...] = ()
    #: Optional real map that replaces the generic prior cell by cell.
    prior_field: FieldSpec | None = None
    #: Only layers explicitly allowed may use simulated readings (project rule: road loops only).
    allow_simulated: bool = False
    #: "none": readings are values. "count": readings are items (e.g. parked scooters) counted per cell.
    aggregate: str = "none"
    aggregate_window_minutes: float = 5.0
    #: Plain-language limits of the layer, repeated in every answer's warnings.
    caveats: tuple[str, ...] = ()
    #: Share of the spread that spreads to neighbouring cells (1 = all; the rest is local, a "nugget").
    spatial_share: float = 1.0
    #: Readings are gathered this far back from the end of a window, at least (daily means arrive a day late).
    history_hours: float = 0.0

    @property
    def source_layers(self) -> tuple[str, ...]:
        return tuple(s.layer for s in self.sources)


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
            correlation_length_km=_num(entry["correlation_length_km"]),
            relax_tau_hours=_num(entry["relax_tau_hours"]),
            min_value=float(entry.get("min_value", float("-inf"))),
            calibration_method=str(calibration.get("method", "loso")),
            calibration_note=str(calibration.get("note", "")),
            sources=tuple(_source(x) for x in entry.get("sources", [])),
            prior_field=None
            if field is None
            else FieldSpec(
                source=str(field["source"]),
                entity_types=tuple(str(t) for t in field["entity_types"]),
                value_key=str(field["value_key"]),
                method=str(field.get("method", "bin")),
                offset=_num(field.get("offset", 0.0)),
                scale=_num(field.get("scale", 1.0)),
                sd=None if field.get("sd") is None else _num(field["sd"]),
                covariate_file=None if field.get("covariate") is None else str(field["covariate"]["file"]),
                covariate_coef=0.0 if field.get("covariate") is None else _num(field["covariate"]["coef"]),
                covariate_center=0.0 if field.get("covariate") is None else _num(field["covariate"]["center"]),
            ),
            allow_simulated=bool(entry.get("allow_simulated", False)),
            aggregate=str(entry.get("aggregate", "none")),
            aggregate_window_minutes=float(entry.get("aggregate_window_minutes", 5.0)),
            caveats=tuple(str(c) for c in entry.get("caveats", [])),
            spatial_share=_num(entry.get("spatial_share", 1.0)),
            history_hours=_num(entry.get("history_hours", 0.0)),
        )
    return specs


def _num(raw: Any) -> float:
    """A number, or a {value, basis} mapping (learned settings carry their basis)."""
    if isinstance(raw, dict):
        return float(raw["value"])
    return float(raw)


def _source(raw: Any) -> SourceSpec:
    if isinstance(raw, str):
        return SourceSpec(layer=raw)
    types = raw.get("entity_types")
    key = raw.get("value_key")
    drop = raw.get("drop_below")
    return SourceSpec(
        layer=str(raw["layer"]),
        entity_types=tuple(str(t) for t in types) if types is not None else None,
        value_key=str(key) if key is not None else None,
        scale=float(raw.get("scale", 1.0)),
        offset=float(raw.get("offset", 0.0)),
        extra_sd=float(raw.get("extra_sd", 0.0)),
        drop_below=float(drop) if drop is not None else None,
    )


def load_calibration_rules(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    rules = _load(config_dir)["calibration_rules"]
    if not isinstance(rules, dict):
        raise ValueError("calibration_rules must be a mapping")
    return rules
