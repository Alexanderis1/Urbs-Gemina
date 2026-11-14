"""crowds and exposure tools: WS4 wrappers around WS5's twin.beliefs.crowds / exposure (faked here)."""
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from twin.tools.crowds_exposure import crowds_view, exposure_count
from twin.tools.envelope import ToolError
from twin.tools.layers import LayerStore
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import Settings

SQUARE = {"type": "Polygon", "coordinates": [[[12.47, 41.89], [12.49, 41.89], [12.49, 41.90], [12.47, 41.90],
                                              [12.47, 41.89]]]}


def _part(**result: Any) -> dict[str, Any]:
    return {"status": "ok", "reason": None, "inputs": {}, "result": result, "data_kinds": {"x": "estimated"},
            "sources": [{"id": "src", "retrieved_at": None}], "synthetic": False, "warnings": ["w"],
            "snapshot_hash": "h"}


@pytest.fixture()
def fake_ws5(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    spec = types.SimpleNamespace(sources=(types.SimpleNamespace(layer="air_quality"),), prior_field=None)
    api = types.ModuleType("twin.beliefs.api")
    api.layer_names = lambda: ["air_no2", "emf"]  # type: ignore[attr-defined]

    def build_layer(name: str, cells: Any, providers: Any, start: Any, end: Any, **kw: Any) -> Any:
        seen["build"] = (name, list(cells), providers)
        return "LAYER"

    api.build_layer = build_layer  # type: ignore[attr-defined]
    grid = types.ModuleType("twin.beliefs.grid")
    grid.cells_in_polygon = lambda geometry, res: ["c1", "c2"]  # type: ignore[attr-defined]
    bconfig = types.ModuleType("twin.beliefs.config")
    bconfig.load_specs = lambda: {"air_no2": spec, "emf": spec}  # type: ignore[attr-defined]
    bconfig.grid_resolution = lambda: 9  # type: ignore[attr-defined]
    crowds = types.ModuleType("twin.beliefs.crowds")

    def crowds_fn(cells: Any, start: Any, end: Any, providers: Any, residents_path: Any = None) -> Any:
        seen["crowds"] = (list(cells), residents_path)
        return _part(cells=[{"cell": "c1", "busy": True}])

    def census_per_cell(path: Any, cells: Any) -> Any:
        seen["census"] = path
        return {"c1": {"residents": 10}}

    crowds.crowds = crowds_fn  # type: ignore[attr-defined]
    crowds.census_per_cell = census_per_cell  # type: ignore[attr-defined]
    exposure = types.ModuleType("twin.beliefs.exposure")

    def exposure_fn(layer: Any, census: Any, threshold: float) -> Any:
        seen["exposure"] = (layer, census, threshold)
        return _part(city={"people_above": {"expected": 3}})

    exposure.exposure = exposure_fn  # type: ignore[attr-defined]
    for mod in (api, grid, bconfig, crowds, exposure):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    return seen


@pytest.fixture()
def runtime(tmp_path: Path) -> ToolRuntime:
    census = tmp_path / "processed" / "census_sections.geojson"
    census.parent.mkdir()
    census.write_text('{"type": "FeatureCollection", "features": []}')
    from dataclasses import replace

    base = Settings.load()
    settings = replace(base, paths=replace(base.paths, data=tmp_path))
    return ToolRuntime(settings=settings, store=LayerStore(tmp_path / "raw", tmp_path / "m.json"))


def test_crowds_wraps_ws5_with_census_and_run_id(runtime: ToolRuntime, fake_ws5: dict[str, Any]) -> None:
    env = crowds_view(runtime, SQUARE)
    assert env["status"] == "ok" and env["tool"] == "crowds" and len(env["run_id"]) == 64
    assert env["result"]["cells"][0]["busy"] is True
    assert env["result"]["area"]["kind"] == "polygon"
    assert fake_ws5["crowds"][0] == ["c1", "c2"]
    assert str(fake_ws5["crowds"][1]).endswith("census_sections.geojson")


def test_exposure_reads_threshold_from_config(runtime: ToolRuntime, fake_ws5: dict[str, Any]) -> None:
    runtime.providers = {"air_quality": object()}  # type: ignore[dict-item]
    env = exposure_count(runtime, "emf", SQUARE, "attention_value")
    assert env["status"] == "ok" and env["tool"] == "exposure"
    layer, census, threshold = fake_ws5["exposure"]
    assert threshold == 15.0 and census == {"c1": {"residents": 10}}
    assert env["result"]["threshold"]["source"]
    assert any("average" in w for w in env["warnings"])  # instantaneous estimate vs averaged legal value


def test_exposure_rejects_threshold_of_another_layer(runtime: ToolRuntime, fake_ws5: dict[str, Any]) -> None:
    with pytest.raises(ToolError):
        exposure_count(runtime, "emf", SQUARE, "no2_hourly_limit")
    with pytest.raises(ToolError):
        exposure_count(runtime, "nonsense", SQUARE, "attention_value")


def test_without_ws5_the_tools_say_not_available(runtime: ToolRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "twin.beliefs.crowds", None)
    env = crowds_view(runtime, SQUARE)
    assert env["status"] == "not_available" and "WS5" in env["reason"]
