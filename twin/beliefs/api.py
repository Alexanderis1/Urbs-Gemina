"""Plain Python API of the belief layers, for the ``query_layer`` tool (WS4).

Typical use::

    cells = cells_in_polygon(area_geojson, grid_resolution())
    layer = build_layer("road_speed", cells, provider, start, end)
    payload = query(layer, threshold=None)

``query`` returns the parts of the shared tool response envelope that only the
belief layer knows (``status``, ``reason``, ``inputs``, ``result``,
``data_kinds``, ``sources``, ``synthetic``, ``warnings``) plus ``snapshot_hash``
for the ``run_id``. ``not_available`` gives the same shape when a layer cannot be
built. The tool API adds ``run_id`` (which also hashes config/beliefs.yaml),
``tool`` and ``cached``, and parses the ``area`` id into cells. No number here comes from a
language model.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np

from twin.beliefs.calibration import CalibrationReport, CalibrationRules, leave_one_station_out
from twin.beliefs.config import LayerSpec, load_calibration_rules, load_specs
from twin.beliefs.grid import bbox_of_cells, cell_boundary
from twin.beliefs.layer import BeliefLayer, assimilate, prior_layer
from twin.providers.base import Observation, Provider, ProviderNotConfigured

Z95 = NormalDist().inv_cdf(0.95)


def layer_names() -> list[str]:
    return sorted(load_specs())


def build_layer(
    name: str,
    cells: Sequence[str],
    provider: Provider | Sequence[Provider] | None,
    start: datetime,
    end: datetime,
    observations: Sequence[Observation] | None = None,
    spec: LayerSpec | None = None,
    prior_provider: Provider | None = None,
) -> BeliefLayer:
    """Starting map at ``start``, then every reading of the providers up to ``end``.

    Several providers are fused: each reading counts according to its own
    ``sigma``. ``prior_provider`` delivers a real gridded map (e.g. Cartoradio)
    used as the per-cell starting point instead of the generic prior.
    """
    spec = spec or load_specs()[name]
    providers: list[Provider]
    if provider is None:
        providers = []
    elif isinstance(provider, Sequence):
        providers = list(provider)
    else:
        providers = [provider]
    bbox = bbox_of_cells(cells)
    field = list(prior_provider.fetch(bbox, start, end)) if prior_provider is not None else None
    layer = prior_layer(spec, cells, start, prior_field=field)
    readings: list[Observation] = list(observations or [])
    for p in providers:
        readings.extend(p.fetch(bbox, start, end))
    return assimilate(layer, readings, until=end)


def layer_payload(
    name: str,
    cells: Sequence[str],
    start: datetime,
    end: datetime,
    providers: Mapping[str, Provider],
    threshold: float | None = None,
) -> dict[str, Any]:
    """One call for the ``query_layer`` tool: pick the sources named in
    config/beliefs.yaml from the active providers, build, and query.

    ``providers`` maps layer names of config/providers.yaml to provider objects
    (the output of ``twin.providers.registry.build_providers``). A layer with no
    real source connected answers ``not_available`` instead of inventing values.
    """
    spec = load_specs()[name]
    feeds = [providers[s] for s in spec.sources if s in providers]
    prior = providers.get(spec.prior_field.source) if spec.prior_field is not None else None
    if not feeds and prior is None:
        wanted = ", ".join(spec.sources) or "none configured"
        return not_available(name, f"no real source is connected for this layer yet (sources: {wanted})")
    try:
        layer = build_layer(name, cells, feeds, start, end, spec=spec, prior_provider=prior)
    except ProviderNotConfigured as exc:
        return not_available(name, str(exc))
    return query(layer, threshold=threshold)


def calibrate(layer: BeliefLayer, observations: Sequence[Observation]) -> BeliefLayer:
    """Run the leave-one-station-out check and attach its verdict to the layer."""
    rules = CalibrationRules.from_config(load_calibration_rules())
    return layer.with_calibration(leave_one_station_out(layer.spec, observations, rules))


def exceedance_probability(mean: float, sd: float, threshold: float) -> float:
    """Probability that the true value is above ``threshold`` (normal belief)."""
    if sd <= 0.0:
        return 1.0 if mean > threshold else 0.0
    return 1.0 - NormalDist(mean, sd).cdf(threshold)


def calibration_of(layer: BeliefLayer) -> CalibrationReport:
    if layer.calibration is not None:
        return layer.calibration
    if layer.spec.calibration_method == "none":
        return CalibrationReport(status="uncalibrated", reason=layer.spec.calibration_note)
    return CalibrationReport(status="uncalibrated", reason="not checked yet (no leave-one-station-out run on this layer)")


def rows(layer: BeliefLayer, cells: Sequence[str] | None = None, threshold: float | None = None) -> list[dict[str, Any]]:
    wanted = layer.cells if cells is None else [c for c in cells if c in layer.index]
    floor = layer.spec.min_value
    out = []
    for cell in wanted:
        i = layer.index[cell]
        mean = float(layer.mean[i])
        sd = math.sqrt(float(layer.variance[i]))
        updated = float(layer.updated_at[i])
        row: dict[str, Any] = {
            "cell": cell,
            "mean": round(mean, 3),
            "sd": round(sd, 3),
            "p5": round(max(floor, mean - Z95 * sd), 3),
            "p50": round(max(floor, mean), 3),
            "p95": round(max(floor, mean + Z95 * sd), 3),
            "updated_at": None if np.isnan(updated) else _iso(datetime.fromtimestamp(updated, tz=timezone.utc)),
            "staleness_s": None if np.isnan(updated) else round(layer.as_of.timestamp() - updated),
        }
        if threshold is not None:
            row["p_exceed"] = round(exceedance_probability(mean, sd, threshold), 4)
        out.append(row)
    return out


def query(layer: BeliefLayer, cells: Sequence[str] | None = None, threshold: float | None = None) -> dict[str, Any]:
    warnings = list(layer.warnings)
    if cells is not None:
        missing = [c for c in cells if c not in layer.index]
        if missing:
            warnings.append(f"{len(missing)} requested cells are not in layer '{layer.spec.name}' and were skipped")
    calibration = calibration_of(layer)
    if calibration.status == "uncalibrated":
        warnings.append(f"uncertainty is uncalibrated: {calibration.reason}")
    if layer.synthetic:
        warnings.append("built from SIMULATED readings: values are illustrative, not measurements")
    if layer.n_observations == 0:
        warnings.append("no readings in the window: values are the prior only")
    return {
        "status": "ok",
        "reason": None,
        "inputs": {
            "layer": layer.spec.name,
            "as_of": _iso(layer.as_of),
            "cells": None if cells is None else list(cells),
            "threshold": threshold,
        },
        "result": {
            "layer": layer.spec.name,
            "unit": layer.spec.unit,
            "as_of": _iso(layer.as_of),
            "grid": f"h3:{layer.resolution}",
            "method": "P1: per-cell Bayesian update + kriging of residuals (sensor fusion weighted by sigma), relaxing to the starting map",
            "n_observations": layer.n_observations,
            "calibration": calibration.status,
            "calibration_report": calibration.as_dict(),
            "cells": rows(layer, cells, threshold),
        },
        "data_kinds": {layer.spec.name: "simulated" if layer.synthetic else "estimated"},
        "sources": [{"id": s, "retrieved_at": _iso(layer.as_of)} for s in layer.sources],
        "synthetic": layer.synthetic,
        "warnings": warnings,
        "snapshot_hash": snapshot_hash(layer),
    }


def not_available(layer_name: str, reason: str) -> dict[str, Any]:
    """Envelope parts for a layer that cannot be built (e.g. its provider has no access yet)."""
    return {
        "status": "not_available",
        "reason": reason,
        "inputs": {"layer": layer_name},
        "result": {},
        "data_kinds": {layer_name: "not_available"},
        "sources": [],
        "synthetic": False,
        "warnings": [f"layer '{layer_name}' is not available: {reason}"],
        "snapshot_hash": None,
    }


def layer_geojson(layer: BeliefLayer, cells: Sequence[str] | None = None, threshold: float | None = None) -> dict[str, Any]:
    """Hexagons with mean, range and staleness, for the map viewer."""
    calibration = calibration_of(layer).status
    features = []
    for row in rows(layer, cells, threshold):
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in cell_boundary(row["cell"])]]},
                "properties": {
                    **row,
                    "layer": layer.spec.name,
                    "unit": layer.spec.unit,
                    "synthetic": layer.synthetic,
                    "calibration": calibration,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def snapshot_hash(layer: BeliefLayer) -> str:
    """SHA-256 of the layer state, an input to the tool ``run_id``."""
    h = hashlib.sha256()
    h.update(f"{layer.spec.name}|{layer.resolution}|{_iso(layer.as_of)}|".encode())
    h.update("|".join(layer.cells).encode())
    h.update(np.round(layer.mean, 6).tobytes())
    h.update(np.round(layer.variance, 6).tobytes())
    return h.hexdigest()


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
