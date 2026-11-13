"""WS4: deterministic tools behind the tool API."""
import math
from pathlib import Path
from typing import Any

import pytest

from twin.tools.area import AreaTooLarge, check_heavy_limit, polygon_area_km2, resolve_area
from twin.tools.data_status import data_status
from twin.tools.envelope import DATA_KINDS, Source, ToolError, compute_run_id, make_envelope
from twin.tools.estimate_field import estimate_field
from twin.tools.geocode import Nominatim, parse_coordinates
from twin.tools.layers import LayerStore
from twin.tools.permit_context import run_context_check
from twin.tools.query_layer import query_layer
from twin.tools.resolve_place import resolve_place
from twin.tools.runtime import BaselineValue, ToolRuntime
from twin.tools.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
LON, LAT = 12.4823, 41.8960  # Piazza Venezia
M_LAT = 111_195.0
M_LON = M_LAT * math.cos(math.radians(LAT))
ENVELOPE_KEYS = {"run_id", "tool", "status", "inputs", "result", "data_kinds", "sources", "synthetic", "warnings",
                 "cached"}


def at(east_m: float, north_m: float) -> list[float]:
    return [LON + east_m / M_LON, LAT + north_m / M_LAT]


def square(half_m: float, cx: float = 0.0, cy: float = 0.0) -> dict[str, Any]:
    ring = [at(cx - half_m, cy - half_m), at(cx + half_m, cy - half_m), at(cx + half_m, cy + half_m),
            at(cx - half_m, cy + half_m), at(cx - half_m, cy - half_m)]
    return {"type": "Polygon", "coordinates": [ring]}


def fc(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


def feat(geometry: dict[str, Any], **props: Any) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": props}


class FixedBaseline:
    def __init__(self, v: float) -> None:
        self.v = v

    def at(self, lon: float, lat: float) -> BaselineValue:
        return BaselineValue(value_v_per_m=self.v, distance_m=20.0,
                             source=Source(id="cartoradio_grid", retrieved_at="2026-11-13T20:00:00+00:00",
                                           sha256="abc"))


@pytest.fixture()
def runtime(tmp_path: Path) -> ToolRuntime:
    settings = Settings.load()
    store = LayerStore(raw_dir=tmp_path / "raw")
    store.add("municipi", fc(feat(square(3000), MUNICIPIO="I", NOME="Municipio I")), sha256="m1")
    store.add("urban_zones", fc(feat(square(800), CODZU="1a", NOME="Centro Storico")), sha256="z1")
    store.add("schools_state", fc(feat({"type": "Point", "coordinates": at(120, 0)}, nome="Liceo Visconti"),
                                  feat({"type": "Point", "coordinates": at(900, 0)}, nome="Too far")), sha256="s1")
    store.add("unesco", fc(feat(square(500))), sha256="u1")
    fetched: list[str] = []

    def fake_fetch(url: str) -> list[dict[str, str]]:
        fetched.append(url)
        return [{"lon": str(at(10, 10)[0]), "lat": str(at(10, 10)[1]), "display_name": "Via del Corso, Roma",
                 "addresstype": "road"}]

    rt = ToolRuntime(settings=settings, store=store,
                     geocoder=Nominatim("https://nominatim.example/search", "test", fetcher=fake_fetch))
    rt.providers = rt._build_providers()
    rt.prg_fetcher = fake_prg
    return rt


def fake_prg(url: str) -> dict[str, Any]:
    """PRG WMS stand-in: 'Citta storica' everywhere, plus 'Verde pubblico' east of the centre."""
    from urllib.parse import parse_qs, urlparse

    w, s, e, n = (float(v) for v in parse_qs(urlparse(url).query)["bbox"][0].split(","))
    features = [{"id": "sr.1", "properties": {"COMPONENTE": "Citta storica", "NORME_TECNICHE_DI_ATTUAZIONE":
                 "<a target='_blank' href='https://example.org/Art_24.htm'>Art.24</a>"}}]
    if (w + e) / 2 > LON + 100 / M_LON:
        features.append({"id": "sr.2", "properties": {"COMPONENTE": "Verde pubblico", "NORME_TECNICHE_DI_ATTUAZIONE": ""}})
    return {"type": "FeatureCollection", "features": features}


# --- envelope -------------------------------------------------------------

def test_envelope_shape_and_run_id_is_deterministic() -> None:
    a = make_envelope("t", {"x": 1}, {"ok": True}, {"layer": "real"}, [Source("s", "now", sha256="h1")])
    b = make_envelope("t", {"x": 1}, {"different": "result"}, {"layer": "real"}, [Source("s", "later", sha256="h1")])
    c = make_envelope("t", {"x": 1}, {}, {"layer": "real"}, [Source("s", "now", sha256="h2")])
    assert set(a) == ENVELOPE_KEYS
    assert a["run_id"] == b["run_id"] == compute_run_id("t", {"x": 1}, {"s": "h1"})
    assert a["run_id"] != c["run_id"]  # new data snapshot -> new run id
    assert a["synthetic"] is False
    assert a["status"] == "ok" and a["cached"] is False and "reason" not in a


def test_envelope_status_needs_a_reason_and_config_changes_run_id() -> None:
    with pytest.raises(ValueError):
        make_envelope("t", {}, None, {}, status="refused")
    refused = make_envelope("t", {}, None, {}, status="refused", reason="too large")
    assert refused["reason"] == "too large"
    one = make_envelope("t", {}, None, {}, config_hashes={"thresholds.yaml": "a"})
    two = make_envelope("t", {}, None, {}, config_hashes={"thresholds.yaml": "b"})
    assert one["run_id"] != two["run_id"]


def test_runtime_envelope_includes_config_hashes(runtime: ToolRuntime) -> None:
    hashes = runtime.settings.config_hashes()
    assert "thresholds.yaml" in hashes and "tools.yaml" in hashes
    env = runtime.envelope("t", {}, None, {})
    assert env["run_id"] == make_envelope("t", {}, None, {}, config_hashes=hashes)["run_id"]


def test_envelope_marks_simulated_as_synthetic_and_rejects_unknown_kinds() -> None:
    assert make_envelope("t", {}, None, {"loops": "simulated"})["synthetic"] is True
    with pytest.raises(ValueError):
        make_envelope("t", {}, None, {"x": "made-up"})


# --- areas ----------------------------------------------------------------

def test_area_city_municipio_zone_and_polygon(runtime: ToolRuntime) -> None:
    city = resolve_area("city", runtime.store, runtime.settings)
    assert city.kind == "city" and city.area_km2 > 1000
    mun = resolve_area("municipio:1", runtime.store, runtime.settings)
    assert mun.id == "municipio:1" and mun.name == "Municipio I"
    assert resolve_area("municipio:I", runtime.store, runtime.settings).id == "municipio:1"
    zone = resolve_area("zone:1a", runtime.store, runtime.settings)
    assert zone.kind == "zone" and zone.id == "zone:1A"
    poly = resolve_area(square(500), runtime.store, runtime.settings)
    assert poly.id.startswith("polygon:") and len(poly.id) == len("polygon:") + 12
    assert city.geometry["type"] == "Polygon" and city.contains(LON, LAT)
    assert poly.area_km2 == pytest.approx(1.0, rel=0.01)
    assert poly.contains(LON, LAT) and not poly.contains(*at(600, 0))


def test_area_parser_works_with_defaults_and_raises_value_error() -> None:
    assert resolve_area("city").id == "city"
    assert resolve_area({"type": "Feature", "geometry": square(200), "properties": {}}).kind == "polygon"
    with pytest.raises(ValueError):
        resolve_area("somewhere")


def test_area_errors_and_heavy_limit(runtime: ToolRuntime) -> None:
    with pytest.raises(ToolError):
        resolve_area("municipio:99", runtime.store, runtime.settings)
    with pytest.raises(ToolError):
        resolve_area({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                     runtime.store, runtime.settings)
    with pytest.raises(AreaTooLarge):
        check_heavy_limit(resolve_area("city", runtime.store, runtime.settings), runtime.settings)
    check_heavy_limit(resolve_area("municipio:1", runtime.store, runtime.settings), runtime.settings)


def test_polygon_area_subtracts_holes() -> None:
    outer = square(500)["coordinates"][0]
    hole = square(100)["coordinates"][0]
    assert polygon_area_km2({"type": "Polygon", "coordinates": [outer, hole]}) == pytest.approx(0.96, rel=0.01)


# --- resolve_place --------------------------------------------------------

def test_coordinates_parse_in_both_orders() -> None:
    assert parse_coordinates("41.896, 12.4823") == (12.4823, 41.896)
    assert parse_coordinates("12.4823 41.896") == (12.4823, 41.896)
    assert parse_coordinates("45.0, 9.0") is None  # Milan is not Rome


def test_resolve_place_from_saved_list_and_locates_municipio(runtime: ToolRuntime) -> None:
    env = resolve_place(runtime, "Piazza Venezia, Roma")
    assert set(env) == ENVELOPE_KEYS
    r = env["result"]
    assert r["found"] and r["method"] == "config_places"
    assert r["municipio"] == {"status": "ok", "id": "1", "name": "Municipio I"}
    assert r["urban_zone"]["id"] == "1A"
    assert env["data_kinds"]["place"] == "estimated"


def test_resolve_place_uses_nominatim_inside_rome(runtime: ToolRuntime) -> None:
    env = resolve_place(runtime, "Via del Corso 1")
    assert env["result"]["method"] == "osm_nominatim"
    assert env["result"]["label"].startswith("Via del Corso")
    assert runtime.geocoder is not None and "bounded=1" in runtime.geocoder.url_for("x")


def test_resolve_place_survives_geocoder_failure(runtime: ToolRuntime) -> None:
    def boom(url: str) -> Any:
        raise OSError("network down")

    runtime.geocoder = Nominatim("https://nominatim.example/search", "test", fetcher=boom)
    env = resolve_place(runtime, "Via Inesistente 3")
    assert env["result"] == {"found": False} and env["status"] == "not_available"
    assert any("Geocoder unavailable" in w for w in env["warnings"])


# --- context_check --------------------------------------------------------

def test_context_check_uses_config_radius_and_flags_missing_layers(runtime: ToolRuntime) -> None:
    env = run_context_check(runtime, LON, LAT)
    r = env["result"]
    assert r["radius_m"] == runtime.settings.thresholds["antenna_context"]["radius_m"]
    assert "not a prohibition" in r["meaning"].lower()
    sensitive = {layer["layer"]: layer for layer in r["groups"]["sensitive_site"]["layers"]}
    assert sensitive["schools_state"]["count"] == 1
    assert sensitive["schools_state"]["hits"][0]["name"] == "Liceo Visconti"
    assert sensitive["schools_state"]["hits"][0]["distance_m"] == pytest.approx(120, abs=1)
    assert sensitive["hospitals"]["status"] == "not_available"
    assert env["data_kinds"]["hospitals"] == "not_available" and env["data_kinds"]["schools_state"] == "real"
    constraints = {layer["layer"]: layer for layer in r["groups"]["constraint"]["layers"]}
    assert constraints["unesco"]["count"] == 1  # inside the UNESCO polygon
    assert r["summary"]["constraint"] == 1 + constraints["prg_sistemi_regole"]["count"]
    assert "Hospitals" in r["not_available"]
    assert any("Hospitals" in w for w in env["warnings"])


def test_context_check_can_hide_properties(runtime: ToolRuntime) -> None:
    env = run_context_check(runtime, LON, LAT, include_properties=False)
    hit = env["result"]["groups"]["sensitive_site"]["layers"][0]["hits"][0]
    assert "properties" not in hit and hit["name"] == "Liceo Visconti"


def test_context_check_rejects_silly_radius(runtime: ToolRuntime) -> None:
    with pytest.raises(ToolError):
        run_context_check(runtime, LON, LAT, radius_m=50_000)


# --- estimate_field -------------------------------------------------------

def test_field_without_baseline_or_antenna_returns_nothing(runtime: ToolRuntime) -> None:
    env = estimate_field(runtime, point={"lon": LON, "lat": LAT})
    assert env["result"] is None and env["status"] == "not_available"
    assert env["data_kinds"]["emf_baseline"] == "not_available"
    assert any("baseline" in w.lower() for w in env["warnings"])


def test_field_with_baseline_and_new_antenna(runtime: ToolRuntime) -> None:
    runtime.baseline = FixedBaseline(1.4)
    antenna = {"lon": at(30, 0)[0], "lat": at(30, 0)[1], "eirp_w": 2000.0, "height_m": 25.0}
    env = estimate_field(runtime, point={"lon": LON, "lat": LAT}, variant={"add_antennas": [antenna]})
    r = env["result"]
    assert r["calibration"] == "uncalibrated"
    assert r["p5"] < r["p50"] < r["p95"]
    expected_new = math.sqrt(30 * 2000.0) / math.hypot(30, 25 - 1.5)
    assert r["new_sources"][0]["field_p50_v_per_m"] == pytest.approx(expected_new, rel=0.01)
    assert r["p50"] == pytest.approx(math.hypot(1.4, expected_new), rel=0.15)
    attention = r["exceedance"]["attention_value"]
    assert attention["threshold_v_per_m"] == runtime.settings.thresholds["emf"]["attention_value_v_per_m"]["value"]
    assert 0.0 <= attention["probability"] <= 1.0
    assert r["exceedance"]["exposure_limit"]["probability"] <= attention["probability"]
    assert env["data_kinds"]["emf_baseline"] == "estimated"
    assert r["baseline"]["credit"].startswith("Fonte: Cartoradio")
    again = estimate_field(runtime, point={"lon": LON, "lat": LAT}, variant={"add_antennas": [antenna]})
    assert again["result"] == r and again["run_id"] == env["run_id"]


def test_field_uses_band_table_and_warns_on_capped_baseline(runtime: ToolRuntime) -> None:
    runtime.baseline = FixedBaseline(15.0)
    env = estimate_field(runtime, point={"lon": LON, "lat": LAT},
                         variant={"add_antennas": [{"lon": LON, "lat": LAT, "band_mhz": 1800}]})
    assert env["result"]["new_sources"][0]["eirp_w"] == 2000
    assert any("15 V/m or more" in w for w in env["warnings"])
    with pytest.raises(ToolError):
        estimate_field(runtime, point={"lon": LON, "lat": LAT}, variant={"add_antennas": [{"lon": LON, "lat": LAT}]})


def test_field_over_an_area(runtime: ToolRuntime) -> None:
    runtime.baseline = FixedBaseline(1.0)
    env = estimate_field(runtime, area=square(300))
    r = env["result"]
    assert r["mode"] == "area" and r["sample_points"] > 4
    assert r["max_p95"] >= r["p50_of_points"]["max"]
    with pytest.raises(ToolError):
        estimate_field(runtime, point={"lon": LON, "lat": LAT}, area="city")


# --- query_layer ----------------------------------------------------------

def test_query_static_layer_in_area(runtime: ToolRuntime) -> None:
    env = query_layer(runtime, "schools_state", area=square(500))
    assert env["result"]["count"] == 1
    assert env["data_kinds"] == {"schools_state": "real"}


def test_query_simulated_provider_layer_is_flagged(runtime: ToolRuntime) -> None:
    env = query_layer(runtime, "traffic_flow", area="city", time="2026-11-13T08:00:00Z")
    assert env["synthetic"] is True
    assert env["data_kinds"]["traffic_flow"] == "simulated"
    assert env["result"]["count"] > 0
    assert all(o["synthetic"] for o in env["result"]["observations"])


def test_query_unknown_or_planned_layer_says_not_available(runtime: ToolRuntime) -> None:
    for name in ("emf_measurements", "nonsense"):  # no provider configured in the test runtime
        env = query_layer(runtime, name)
        assert env["status"] == "not_available" and env["reason"]
        assert env["data_kinds"] == {name: "not_available"}
    with pytest.raises(ToolError):
        query_layer(runtime, "traffic_flow", time="yesterday")


def test_citizen_gets_aggregates_for_office_only_layers(runtime: ToolRuntime) -> None:
    runtime.settings.tools["api"]["office_only_detail_layers"].append("traffic_flow")
    env = query_layer(runtime, "traffic_flow", time="2026-11-13T08:00:00Z", role="citizen")
    assert env["result"]["type"] == "aggregate"
    assert "observations" not in env["result"]
    assert sum(c["count"] for c in env["result"]["cells"]) == env["result"]["total"]


# --- data_status ----------------------------------------------------------

def test_data_status_lists_every_configured_layer(runtime: ToolRuntime) -> None:
    env = data_status(runtime)
    rows = {row["layer"]: row for row in env["result"]["layers"]}
    assert set(rows) == set(runtime.settings.providers)
    assert rows["traffic_flow"]["status"] == "active" and rows["traffic_flow"]["data_kind"] == "simulated"
    assert rows["emf_baseline"]["data_kind"] == "estimated"
    assert set(env["data_kinds"].values()) <= DATA_KINDS
    assert env["synthetic"] is True


# --- permit report --------------------------------------------------------

def test_permit_report_cites_every_tool_run(runtime: ToolRuntime) -> None:
    from twin.modules.antennas.report import DISCLAIMER, build_permit_report

    runtime.baseline = FixedBaseline(1.4)
    env = build_permit_report(runtime, place="Piazza Venezia",
                              proposed_antennas=[{"lon": at(30, 0)[0], "lat": at(30, 0)[1], "eirp_w": 2000}])
    r = env["result"]
    md = r["markdown"]
    assert [run["tool"] for run in r["tool_runs"]] == ["resolve_place", "context_check", "estimate_field"]
    for run in r["tool_runs"]:
        assert run["run_id"] in md
    assert DISCLAIMER in md
    assert "Not a prohibition" in md
    assert "Fonte: Cartoradio" in md
    assert "Liceo Visconti" in md
    assert r["report_sha256"] == __import__("hashlib").sha256(md.encode()).hexdigest()


def test_permit_report_without_data_says_insufficient(runtime: ToolRuntime) -> None:
    from twin.modules.antennas.report import build_permit_report

    env = build_permit_report(runtime, point={"lon": LON, "lat": LAT}, role="citizen")
    assert "Insufficient data" in env["result"]["markdown"]
    with pytest.raises(ToolError):
        build_permit_report(runtime)


def test_resolve_entry_point_for_other_modules() -> None:
    from twin.tools.resolve_place import resolve

    env = resolve("41.896, 12.4823")
    assert env["status"] == "ok" and env["result"]["lon"] == 12.4823


def test_nominatim_precision_labels() -> None:
    from twin.tools.geocode import nominatim_precision

    assert nominatim_precision({"category": "place", "type": "house", "addresstype": "place"}) == "house"
    assert nominatim_precision({"category": "building", "type": "yes", "addresstype": "building"}) == "house"
    assert nominatim_precision({"category": "highway", "type": "residential", "addresstype": "road"}) == "road"


def test_only_traffic_loops_may_be_simulated(runtime: ToolRuntime) -> None:
    from twin.providers.simulated.loops import SimLoopsProvider

    assert runtime.settings.tools["allowed_simulated_layers"] == ["traffic_flow"]
    runtime.settings.providers["air_quality"] = "sim_loops"  # pretend a simulator feeds air quality
    runtime.providers["air_quality"] = SimLoopsProvider(seed=1, n_stations=3)
    env = query_layer(runtime, "air_quality", time="2026-11-13T08:00:00Z")
    assert env["status"] == "refused"
    status = data_status(runtime)
    assert "air_quality" in status["result"]["simulation_violations"]
    assert "traffic_flow" not in status["result"]["simulation_violations"]
    assert not runtime.simulation_allowed("emf_baseline", SimLoopsProvider(seed=1, n_stations=1))


def test_layer_store_falls_back_to_processed(tmp_path: Path) -> None:
    import json as _json

    (tmp_path / "processed").mkdir()
    zone = {"type": "FeatureCollection", "features": [feat(square(400), code_zu="1A", denominazione="Centro Storico")]}
    (tmp_path / "processed" / "urban_zones.geojson").write_text(_json.dumps(zone))
    store = LayerStore(raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed")
    area = resolve_area("zone:1a", store, Settings.load())
    assert area.id == "zone:1A" and area.name == "Centro Storico"


def test_field_reports_nearest_real_measurement(runtime: ToolRuntime) -> None:
    from twin.modules.antennas.report import build_permit_report

    runtime.baseline = FixedBaseline(1.4)
    runtime.measurements = FixedBaseline(0.9)
    env = estimate_field(runtime, point={"lon": LON, "lat": LAT})
    assert env["result"]["nearest_measurement"]["value_v_per_m"] == 0.9
    assert env["data_kinds"]["emf_measurements"] == "real"
    md = build_permit_report(runtime, point={"lon": LON, "lat": LAT})["result"]["markdown"]
    assert "Nearest real measurement" in md


def test_prg_is_sampled_live_with_nearest_distance(runtime: ToolRuntime) -> None:
    env = run_context_check(runtime, LON, LAT)
    prg = next(l for l in env["result"]["groups"]["constraint"]["layers"] if l["layer"] == "prg_sistemi_regole")
    names = {h["name"]: h for h in prg["hits"]}
    assert names["Citta storica"]["distance_m"] == 0.0
    assert names["Citta storica"]["properties"]["nta_articles"] == [{"article": "Art.24", "url": "https://example.org/Art_24.htm"}]
    assert names["Verde pubblico"]["distance_m"] == 150.0
    assert any("not exhaustive" in w for w in env["warnings"])


def test_prg_failure_is_reported_not_raised(runtime: ToolRuntime) -> None:
    from twin.tools import prg

    prg._CACHE.clear()

    def down(url: str) -> Any:
        raise OSError("server down")

    runtime.prg_fetcher = down
    env = run_context_check(runtime, LON + 0.01, LAT)
    assert env["data_kinds"]["prg_sistemi_regole"] == "not_available"
    assert any("live query failed" in w for w in env["warnings"])
    prg._CACHE.clear()


def test_belief_layer_uses_ws5_layer_payload_and_survives_a_failing_feed(
        runtime: ToolRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    """With WS5's layer_payload, only that call picks the feeds; a feed that errors is skipped with a warning."""
    import sys
    import types

    class Broken:
        kind = "open"

        def fetch(self, bbox: Any, start: Any, end: Any) -> list[Any]:
            raise RuntimeError("upstream down")

    seen: dict[str, Any] = {}

    def layer_payload(name: str, cells: Any, start: Any, end: Any, providers: Any) -> dict[str, Any]:
        seen["providers"] = providers
        assert providers["rain"].fetch(None, start, end) == []  # wrapped: no exception
        return {"status": "ok", "result": {"layer": name, "cells": [{"cell": "a"}]}, "data_kinds": {name: "estimated"},
                "sources": [], "warnings": []}

    api = types.ModuleType("twin.beliefs.api")
    api.layer_names = lambda: ["rain"]  # type: ignore[attr-defined]
    api.layer_payload = layer_payload  # type: ignore[attr-defined]
    grid = types.ModuleType("twin.beliefs.grid")
    grid.cells_in_polygon = lambda geometry, res: ["a"]  # type: ignore[attr-defined]
    bconfig = types.ModuleType("twin.beliefs.config")
    bconfig.load_specs = lambda: {"rain": object()}  # type: ignore[attr-defined]
    bconfig.grid_resolution = lambda: 9  # type: ignore[attr-defined]
    for mod in (api, grid, bconfig):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    runtime.providers = {"rain": Broken()}  # type: ignore[dict-item]
    env = query_layer(runtime, "rain", area=square(200))
    assert env["status"] == "ok" and env["result"]["count"] == 1
    assert any("upstream down" in w or "rain" in w for w in env["warnings"])
