"""Citizen service: sports venues and museums open at a chosen day and time."""
from pathlib import Path
from typing import Any

import pytest

from twin.modules.sports.model import Facility, FieldValue
from twin.tools import places_open as po
from twin.tools.envelope import ToolError
from twin.tools.layers import LayerStore
from twin.tools.runtime import ToolRuntime
from twin.tools.settings import Settings

POINT = [12.4823, 41.8960]
SATURDAY_11 = "2026-11-14T10:00:00Z"   # 11:00 in Rome


def museum(dx: float, name: str, hours: str | None, kind: str = "museum") -> dict[str, Any]:
    props: dict[str, Any] = {"name": name, "tourism": kind, "addr:street": "Via X", "addr:housenumber": "1"}
    if hours:
        props["opening_hours"] = hours
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [POINT[0] + dx, POINT[1]]}, "properties": props}


@pytest.fixture()
def rt(tmp_path: Path) -> ToolRuntime:
    store = LayerStore(raw_dir=tmp_path / "raw")
    store.add("museums_osm", {"type": "FeatureCollection", "features": [
        museum(0.001, "Museo aperto", "Tu-Su 09:00-19:00"),
        museum(0.0005, "Museo chiuso il sabato", "Mo-Fr 09:00-19:00"),
        museum(0.002, "Galleria senza orari", None, kind="gallery"),
        museum(0.5, "Museo lontano", "Tu-Su 09:00-19:00"),
    ]}, sha256="m1")
    return ToolRuntime(settings=Settings.load(), store=store)


def test_museums_open_first_then_nearest(rt: ToolRuntime) -> None:
    env = po.places_open(rt, "museum", SATURDAY_11, point=POINT, radius_m=2000)
    places = env["result"]["places"]
    assert [p["name"] for p in places] == ["Museo aperto", "Galleria senza orari", "Museo chiuso il sabato"]
    assert places[0]["open_at"] is True and places[1]["open_at"] is None and places[2]["open_at"] is False
    assert places[0]["address"] == "Via X 1" and places[1]["category"] == "galleria"
    assert env["result"]["coverage"] == {"with_hours": 2, "total": 3}
    assert env["data_kinds"]["museums_osm"] == "real"


def fv(value: Any) -> FieldValue:
    return FieldValue(value=value, status="open_data")


def facility(fid: str, name: str, dx: float, hours: str | None, disciplines: list[str], **extra: Any) -> Facility:
    return Facility(facility_id=fid, lon=POINT[0] + dx, lat=POINT[1],
                    fields={"name": fv(name), "kind": fv("sports_centre"), "hours": fv(hours), "address": fv("Via Y 2")},
                    disciplines={d: fv(True) for d in disciplines}, members=(f"osm:{fid}",),
                    extra={k: fv(v) for k, v in extra.items()})


def test_sports_filter_by_discipline_and_hours(rt: ToolRuntime) -> None:
    facilities = [facility("a", "Piscina aperta", 0.001, "Mo-Sa 07:00-22:00", ["swimming"]),
                  facility("b", "Piscina chiusa", 0.0005, "Mo-Fr 07:00-22:00", ["swimming"]),
                  facility("c", "Campo calcio", 0.0002, "Mo-Su 08:00-23:00", ["football"]),
                  facility("d", "Piscina privata", 0.0001, "24/7", ["swimming"], access="private"),
                  facility("e", "Piscina orari italiani", 0.003, "Lun-Sab 8-20", ["swimming"])]
    env = po.places_open(rt, "sport", SATURDAY_11, point=POINT, sport="nuoto", facilities=facilities)
    names = [p["name"] for p in env["result"]["places"]]
    assert names == ["Piscina aperta", "Piscina orari italiani", "Piscina chiusa"]
    assert env["result"]["sport"] == "swimming"


def test_unknown_kind_is_refused(rt: ToolRuntime) -> None:
    with pytest.raises(ToolError):
        po.places_open(rt, "cinema", SATURDAY_11)
