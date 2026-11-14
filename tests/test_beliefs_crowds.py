"""Crowds view: several real activity signals side by side, plus where they agree."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from twin.beliefs.config import load_specs
from twin.beliefs.crowds import crowds, residents_per_cell
from twin.beliefs.grid import cell_boundary, cell_of, cells_in_bbox
from twin.providers.base import BBox, Observation, ProviderInfo

T0 = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
WINDOW = (12.46, 41.88, 12.50, 41.91)
BUSY = (12.48, 41.895)
QUIET = (12.47, 41.885)


class Feed:
    def __init__(self, pid: str, obs: list[Observation]) -> None:
        self._pid, self._obs = pid, obs

    def describe(self) -> ProviderInfo:
        return ProviderInfo(self._pid, "open", "x", "test", "hourly", False)

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        return iter(self._obs)


def item(kind: str, key: str, lon: float, lat: float, value: float = 1.0, sigma: float = 0.0, source: str = "x") -> Observation:
    return Observation(f"{source}-{lon}-{lat}", kind, lon, lat, T0, {key: value}, {key: sigma}, source, False)


def providers() -> dict[str, Feed]:
    wifi = [item("CrowdFlowObserved", "peopleCount", *BUSY, value=50.0, sigma=7.0, source="roma_wifi"),
            item("CrowdFlowObserved", "peopleCount", *QUIET, value=2.0, sigma=1.4, source="roma_wifi"),
            item("CrowdFlowObserved", "peopleCount", 12.495, 41.905, value=3.0, sigma=1.7, source="roma_wifi")]
    scooters = [item("MicromobilityVehicle", "availableVehicles", *BUSY, source="bird_gbfs") for _ in range(8)]
    scooters += [item("MicromobilityVehicle", "availableVehicles", 12.462, 41.882, source="bird_gbfs"),
                 item("MicromobilityVehicle", "availableVehicles", 12.498, 41.908, source="bird_gbfs")]
    buses = [item("ScheduledVehicle", "scheduledVehicles", *BUSY, source="roma_gtfs_schedule") for _ in range(5)]
    buses.append(item("ScheduledVehicle", "scheduledVehicles", 12.462, 41.882, source="roma_gtfs_schedule"))
    return {"activity_wifi": Feed("roma_wifi", wifi), "micromobility": Feed("bird_gbfs", scooters),
            "transit_schedule": Feed("roma_gtfs_schedule", buses)}


def test_transit_supply_layer_counts_scheduled_vehicles() -> None:
    spec = load_specs()["transit_supply"]
    assert spec.aggregate == "count" and spec.source_layers == ("transit_schedule",)


def test_signals_side_by_side_and_agreement() -> None:
    cells = cells_in_bbox(WINDOW, 9)
    out = crowds(cells, T0, T0, providers())
    assert out["status"] == "ok"
    rows = {r["cell"]: r for r in out["result"]["cells"]}
    busy = rows[cell_of(*BUSY, 9)]
    assert set(busy["signals"]) == {"wifi_sessions", "activity", "transit_supply"}
    assert busy["signals"]["wifi_sessions"]["mean"] > 30
    assert busy["agree"] >= 2 and busy["busy"] is True
    quiet = rows[cell_of(*QUIET, 9)]
    assert quiet["busy"] is False
    assert out["data_kinds"]["wifi_sessions"] == "real"
    assert out["data_kinds"]["transit_supply"] == "estimated"
    assert out["data_kinds"]["residents"] == "not_available"
    assert any("lower bound" in w for w in out["warnings"])


def test_missing_feed_is_reported_not_invented() -> None:
    feeds = providers()
    del feeds["micromobility"]
    out = crowds(cells_in_bbox(WINDOW, 9), T0, T0, feeds)
    assert out["data_kinds"]["activity"] == "not_available"
    row = next(r for r in out["result"]["cells"] if r["cell"] == cell_of(*BUSY, 9))
    assert "activity" not in row["signals"]


def test_residents_from_census_sections(tmp_path: Path) -> None:
    cell = cell_of(*BUSY, 9)
    ring = [list(p) for p in cell_boundary(cell)]
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"sez_id": "1", "residents": 120}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}
    path = tmp_path / "census.geojson"
    path.write_text(json.dumps(gj))
    cells = cells_in_bbox(WINDOW, 9)
    assert residents_per_cell(path, cells)[cell] == 120
    out = crowds(cells, T0, T0, providers(), residents_path=path)
    row = next(r for r in out["result"]["cells"] if r["cell"] == cell)
    assert row["signals"]["residents"]["mean"] == 120
    assert out["data_kinds"]["residents"] == "real"
