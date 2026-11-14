"""Tool registry: name -> request model + handler. Shared by the HTTP app and the schema export."""
from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from pydantic import BaseModel

from twin.api import models as m
from twin.modules.antennas.report import build_permit_report
from twin.tools.area import AreaTooLarge, resolve_area
from twin.tools.layers import LayerSnapshot
from twin.tools.crowds_exposure import check_sensors_tool, crowds_view, exposure_count, site_values_at
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


def _scenario_data(rt: ToolRuntime, kind: str, area: Any, change: Mapping[str, Any]) -> Any:
    """Inputs the WS6 engine reads, built from this runtime (baseline, boundaries, snapshot hashes).

    When WS6 ships ``twin.scenarios.baselines.live_data`` its real Cartoradio grid is the baseline
    and ours only adds boundaries and census; if that call fails we fall back to our point baseline.
    """
    data_mod = importlib.import_module("twin.scenarios.data")
    sigma_db = float(rt.settings.tool("estimate_field", "baseline_sigma_db"))
    baseline = rt.baseline

    def baseline_field(lon: float, lat: float) -> Any:
        found = baseline.at(lon, lat) if baseline is not None else None
        return None if found is None else data_mod.FieldSample(found.value_v_per_m, sigma_db)

    def area_lookup(name: str) -> Any:
        resolved = resolve_area(name, rt.store, rt.settings)
        return resolved.geometry

    census = _census(rt)
    snapshots = {key: snap.sha256 for key in ("municipi", "urban_zones") if (snap := rt.store.get(key)) is not None}
    if census is not None:
        snapshots["census_sections"] = census.sha256
    common: dict[str, Any] = {
        "census": {"type": "FeatureCollection", "features": census.features} if census is not None else None,
        "census_source": census.source().to_dict() if census is not None else None,
        "area_lookup": area_lookup,
        "snapshots": snapshots,
    }
    try:
        live = importlib.import_module("twin.scenarios.baselines").live_data
    except (ImportError, AttributeError):
        live = None
    if live is not None:
        try:
            return live(kind, area, change, **{**common, "snapshots": dict(snapshots)})
        except Exception:  # noqa: BLE001 - city/Cartoradio server down: use our own baseline instead
            pass
    return data_mod.ScenarioData(
        baseline_field=baseline_field if baseline is not None else None,
        baseline_source={"id": "cartoradio_grid"} if baseline is not None else None,
        **common,
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
        out: dict[str, Any] = engine.run(req.kind, area, req.change, data=_scenario_data(rt, req.kind, area, req.change))
    except (area_mod.AreaTooLarge, AreaTooLarge) as error:
        return make_envelope("run_scenario", inputs, None, {}, status="refused", reason=str(error),
                             config_hashes=rt.settings.config_hashes())
    except (area_mod.AreaNotAvailable, ToolError) as error:
        return make_envelope("run_scenario", inputs, None, {}, status="not_available", reason=str(error),
                             config_hashes=rt.settings.config_hashes())
    except ValueError as error:  # the engine rejects the 'change' shape: tell the caller what it needs
        return make_envelope("run_scenario", inputs, None, {}, status="refused", reason=str(error),
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


def _sports_area(rt: ToolRuntime, area: Any) -> Any:
    """WS10 wants zones as polygons; other area forms pass through unchanged."""
    if isinstance(area, str) and area.lower().startswith(("zone:", "urban_zone:", "zu:")):
        return resolve_area(area, rt.store, rt.settings).geometry
    return area


def _sports_inputs(rt: ToolRuntime) -> tuple[Any, Any, Any, list[Any]]:
    """WS10 modules, facility list and config; raises ImportError / OSError when missing."""
    tools_mod = importlib.import_module("twin.modules.sports.tools")
    pipeline = importlib.import_module("twin.modules.sports.pipeline")
    config_mod = importlib.import_module("twin.modules.sports.config")
    path = rt.settings.paths.data / str(rt.settings.tool("sports", "facilities_file"))
    return tools_mod, config_mod.load_config(), pipeline, list(pipeline.load_facilities(path))


def _census(rt: ToolRuntime) -> LayerSnapshot | None:
    """Census sections from WS1 (data/processed/census_sections.geojson): sez_id, residents, children_0_14,
    municipio, zone."""
    path = rt.settings.paths.data / "processed" / "census_sections.geojson"
    if not path.exists():
        return None
    payload = path.read_bytes()
    return LayerSnapshot.from_collection("census_sections", json.loads(payload),
                                         sha256=hashlib.sha256(payload).hexdigest())


def _population(rt: ToolRuntime) -> list[Any]:
    """Census sections -> WS10 PopulationPoint list (WS10 owns the conversion); empty when not built."""
    deserts = importlib.import_module("twin.modules.sports.deserts")
    census = _census(rt)
    if census is None:
        return []
    points: list[Any] = deserts.population_from_census({"type": "FeatureCollection", "features": census.features})
    return points


def _sports_facilities(rt: ToolRuntime, req: m.SportsFacilitiesIn, role: str) -> dict[str, Any]:
    inputs = req.model_dump(exclude_none=True)
    try:
        tools_mod, config, _, facilities = _sports_inputs(rt)
    except ImportError:
        return _not_wired("sports_facilities", "twin.modules.sports.tools", "sports_facilities",
                          "WS10 (sports add-on)", inputs)
    except OSError as error:
        return make_envelope("sports_facilities", inputs, None, {"sports_facilities": "not_available"},
                             status="not_available", reason=f"Facility layer not built yet ({error}). "
                             "Run: python -m twin.modules.sports.pipeline build")
    out: dict[str, Any] = tools_mod.sports_facilities(_sports_area(rt, _dump(req.area)), req.discipline,
                                                      facilities, config, type=req.type,
                                                      accessible=req.accessible)
    return out


def _sport_coverage(rt: ToolRuntime, req: m.SportCoverageIn, role: str) -> dict[str, Any]:
    inputs = req.model_dump(exclude_none=True)
    try:
        tools_mod, config, _, facilities = _sports_inputs(rt)
        deserts = importlib.import_module("twin.modules.sports.deserts")
    except ImportError:
        return _not_wired("sport_coverage", "twin.modules.sports.tools", "sport_coverage",
                          "WS10 (sports add-on)", inputs)
    except OSError as error:
        return make_envelope("sport_coverage", inputs, None, {"sports_facilities": "not_available"},
                             status="not_available", reason=f"Facility layer not built yet ({error}). "
                             "Run: python -m twin.modules.sports.pipeline build")
    gyms = [deserts.school_gym_facility(g.name, g.lon, g.lat, config, g.disciplines) for g in req.open_school_gyms]
    out: dict[str, Any] = tools_mod.sport_coverage(_sports_area(rt, _dump(req.area)), req.discipline, facilities,
                                                   _population(rt), config, max_minutes=req.max_minutes,
                                                   open_facilities=gyms)
    return out


TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in [
    ToolSpec("resolve_place", m.ResolvePlaceIn, lambda rt, req, role: resolve_place(rt, req.text)),
    ToolSpec("context_check", m.ContextCheckIn,
             lambda rt, req, role: run_context_check(rt, req.point[0], req.point[1], req.radius_m,
                                                     include_properties=role == "office")),
    ToolSpec("estimate_field", m.EstimateFieldIn, _estimate_field),
    ToolSpec("query_layer", m.QueryLayerIn,
             lambda rt, req, role: query_layer(rt, req.layer, _dump(req.area), req.time, req.limit, role)),
    ToolSpec("crowds", m.CrowdsIn, lambda rt, req, role: crowds_view(rt, _dump(req.area), req.time), owner="WS5"),
    ToolSpec("exposure", m.ExposureIn,
             lambda rt, req, role: exposure_count(rt, req.layer, _dump(req.area), req.threshold, req.time),
             owner="WS5"),
    ToolSpec("site_values", m.SiteValuesIn,
             lambda rt, req, role: site_values_at(rt, req.layer, _dump(req.area), req.threshold, req.categories,
                                                  req.limit, req.time), owner="WS5"),
    ToolSpec("check_sensors", m.CheckSensorsIn,
             lambda rt, req, role: check_sensors_tool(rt, req.layer, _dump(req.area), req.time), owner="WS5"),
    ToolSpec("run_scenario", m.RunScenarioIn, _run_scenario, owner="WS6"),
    ToolSpec("legal_lookup", m.LegalLookupIn, _legal_lookup, owner="WS7"),
    ToolSpec("find_dataset", m.FindDatasetIn, _find_dataset, owner="WS7"),
    ToolSpec("data_status", m.DataStatusIn, lambda rt, req, role: data_status(rt)),
    ToolSpec("permit_report", m.PermitReportIn, _permit_report),
    ToolSpec("sports_facilities", m.SportsFacilitiesIn, _sports_facilities, owner="WS10"),
    ToolSpec("sport_coverage", m.SportCoverageIn, _sport_coverage, owner="WS10"),
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
