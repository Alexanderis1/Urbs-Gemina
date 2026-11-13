"""Tool registry: name -> request model + handler. Shared by the HTTP app and the schema export."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from twin.api import models as m
from twin.modules.antennas.report import build_permit_report
from twin.tools.area import AreaTooLarge, resolve_area
from twin.tools.data_status import data_status
from twin.tools.envelope import ToolError, make_envelope
from twin.tools.estimate_field import estimate_field
from twin.tools.permit_context import run_context_check
from twin.tools.query_layer import query_layer
from twin.tools.resolve_place import resolve_place
from twin.tools.runtime import ToolRuntime

Handler = Callable[[ToolRuntime, Any, str], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    model: type[BaseModel]
    handler: Handler
    owner: str = "WS4"

    @property
    def description(self) -> str:
        return " ".join((self.model.__doc__ or self.name).split())


def _dump(value: Any) -> Any:
    return value.model_dump(exclude_none=True) if isinstance(value, BaseModel) else value


def _point(value: list[float] | None) -> dict[str, float] | None:
    return None if value is None else {"lon": value[0], "lat": value[1]}


def _not_wired(tool: str, module_name: str, function: str, owner: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return make_envelope(tool, inputs, None, {}, status="not_available",
                         reason=f"'{tool}' is not wired in this deployment yet: {owner} provides "
                                f"{module_name}.{function}.")


def _delegate(tool: str, module_name: str, function: str, owner: str, inputs: dict[str, Any],
              call: Callable[[Callable[..., dict[str, Any]]], dict[str, Any]]) -> dict[str, Any]:
    try:
        target = getattr(importlib.import_module(module_name), function)
    except (ImportError, AttributeError):
        return _not_wired(tool, module_name, function, owner, inputs)
    try:
        return call(target)
    except Exception as error:  # noqa: BLE001 - e.g. missing API key: report, never crash the API
        return make_envelope(tool, inputs, None, {}, status="not_available",
                             reason=f"{type(error).__name__}: {error}")


def _scenario_data(rt: ToolRuntime) -> Any:
    """Inputs the WS6 engine reads, built from this runtime (baseline, boundaries, snapshot hashes)."""
    data_mod = importlib.import_module("twin.scenarios.data")
    sigma_db = float(rt.settings.tool("estimate_field", "baseline_sigma_db"))
    baseline = rt.baseline

    def baseline_field(lon: float, lat: float) -> Any:
        found = baseline.at(lon, lat) if baseline is not None else None
        return None if found is None else data_mod.FieldSample(found.value_v_per_m, sigma_db)

    def area_lookup(name: str) -> Any:
        resolved = resolve_area(name, rt.store, rt.settings)
        return resolved.geometry

    snapshots = {key: snap.sha256 for key in ("municipi", "urban_zones", "census_sections")
                 if (snap := rt.store.get(key)) is not None}
    census = rt.store.get("census_sections")
    return data_mod.ScenarioData(
        baseline_field=baseline_field if baseline is not None else None,
        baseline_source={"id": "cartoradio_grid"} if baseline is not None else None,
        census={"type": "FeatureCollection", "features": census.features} if census is not None else None,
        census_source=census.source().to_dict() if census is not None else None,
        area_lookup=area_lookup,
        snapshots=snapshots,
    )


def _run_scenario(rt: ToolRuntime, req: m.RunScenarioIn, role: str) -> dict[str, Any]:
    area = _dump(req.area)
    inputs = {"kind": req.kind, "area": area, "change": req.change}
    try:
        engine = importlib.import_module("twin.scenarios.engine")
        area_mod = importlib.import_module("twin.scenarios.area")
    except ImportError:
        return _not_wired("run_scenario", "twin.scenarios.engine", "run", "WS6 (scenario engine)", inputs)
    if req.kind not in engine.kinds():
        raise ToolError(f"unknown scenario kind '{req.kind}'. Known: {', '.join(sorted(engine.kinds()))}")
    try:
        out: dict[str, Any] = engine.run(req.kind, area, req.change, data=_scenario_data(rt))
    except (area_mod.AreaTooLarge, AreaTooLarge) as error:
        return make_envelope("run_scenario", inputs, None, {}, status="refused", reason=str(error),
                             config_hashes=rt.settings.config_hashes())
    except (area_mod.AreaNotAvailable, ToolError) as error:
        return make_envelope("run_scenario", inputs, None, {}, status="not_available", reason=str(error),
                             config_hashes=rt.settings.config_hashes())
    result = out.get("result") or {}
    if "status" not in out:
        out["status"] = result.get("status", "ok") if isinstance(result, dict) else "ok"
        if out["status"] != "ok":
            out["reason"] = str(result.get("reason", "not available"))
    out.setdefault("cached", False)
    return out


def _legal_lookup(rt: ToolRuntime, req: m.LegalLookupIn, role: str) -> dict[str, Any]:
    return _delegate("legal_lookup", "agents.exa_tools", "legal_lookup", "WS7 (agents + Exa)",
                     {"question": req.question}, lambda fn: fn(req.question))


def _find_dataset(rt: ToolRuntime, req: m.FindDatasetIn, role: str) -> dict[str, Any]:
    return _delegate("find_dataset", "agents.exa_tools", "find_dataset", "WS7 (agents + Exa)",
                     {"need": req.need}, lambda fn: fn(req.need))


def _estimate_field(rt: ToolRuntime, req: m.EstimateFieldIn, role: str) -> dict[str, Any]:
    return estimate_field(rt, point=_point(req.point), area=_dump(req.area), variant=_dump(req.variant))


def _permit_report(rt: ToolRuntime, req: m.PermitReportIn, role: str) -> dict[str, Any]:
    antennas = [a.model_dump(exclude_none=True) for a in req.proposed_antennas or []]
    return build_permit_report(rt, place=req.place, point=_point(req.point), proposed_antennas=antennas or None,
                               radius_m=req.radius_m, role=role)


TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in [
    ToolSpec("resolve_place", m.ResolvePlaceIn, lambda rt, req, role: resolve_place(rt, req.text)),
    ToolSpec("context_check", m.ContextCheckIn,
             lambda rt, req, role: run_context_check(rt, req.point[0], req.point[1], req.radius_m,
                                                     include_properties=role == "office")),
    ToolSpec("estimate_field", m.EstimateFieldIn, _estimate_field),
    ToolSpec("query_layer", m.QueryLayerIn,
             lambda rt, req, role: query_layer(rt, req.layer, _dump(req.area), req.time, req.limit, role)),
    ToolSpec("run_scenario", m.RunScenarioIn, _run_scenario, owner="WS6"),
    ToolSpec("legal_lookup", m.LegalLookupIn, _legal_lookup, owner="WS7"),
    ToolSpec("find_dataset", m.FindDatasetIn, _find_dataset, owner="WS7"),
    ToolSpec("data_status", m.DataStatusIn, lambda rt, req, role: data_status(rt)),
    ToolSpec("permit_report", m.PermitReportIn, _permit_report),
]}


def tool_schema(spec: ToolSpec) -> dict[str, Any]:
    """Tool definition in the shape LLM tool-calling APIs expect, plus the output envelope."""
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.model.model_json_schema(),
        "output_schema": {"$ref": "envelope.json"},
        "http": {"method": "POST", "path": f"/tools/{spec.name}"},
        "owner": spec.owner,
    }
