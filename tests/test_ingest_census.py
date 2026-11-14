import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
pd = pytest.importorskip("pandas")
pytest.importorskip("openpyxl")
from shapely.geometry import box  # noqa: E402

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import HttpRequest  # noqa: E402
from twin.ingest.static import ingest_layer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
LAYER = CATALOG.layers["census_sections"]


def shapes_zip(tmp: Path) -> bytes:
    frame = gpd.GeoDataFrame(
        {"PRO_COM": [58091, 58091, 58091, 58001],
         "SEZ21_ID": [580911010001.0, 580911010002.0, 580911010003.0, 580011000001.0],
         "COM_ASC1": [58091001.0, 58091001.0, 58091015.0, 58001000.0],
         "COM_ASC3": [58091080.0, 58091080.0, 58091002.0, 0.0],
         "POP21": [10.0, 84.0, 0.0, 5.0]},
        geometry=[box(790000, 4640000, 790100, 4640100), box(790100, 4640000, 790200, 4640100),
                  box(790200, 4640000, 790300, 4640100), box(0, 0, 1, 1)],
        crs="EPSG:32632",
    )
    folder = tmp / "SHP"
    folder.mkdir()
    frame.to_file(folder / "R12_21_WGS84.shp")
    zones = "COD_REG\tCOD_UTS\tPRO_COM\tCOM_ASC3\tCOD_ASC3\tCOD_ASC3_T\tDEN_ASC3\tTIPO_ASC3\r\n" \
            "12\t258\t58091\t58091080\t80\t1a\tCentro Storico\tZona Urbanistica\r\n" \
            "12\t258\t58091\t58091002\t2\t10a\tDon Bosco\tZona Urbanistica\r\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in folder.iterdir():
            archive.write(path, f"SHP/{path.name}")
        archive.writestr("TAB/ASC3_R12_21.csv", zones.encode("utf-16"))
    return buffer.getvalue()


def population_zip() -> bytes:
    sheet = pd.DataFrame({"SEZ21_ID": [580911010001, 580911010002],
                          "P1": [10, 84], "P14": [0, 1], "P15": [2, 4], "P16": [0, 2]})
    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx) as writer:
        sheet.to_excel(writer, sheet_name="Roma_2021", index=False)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Roma_indicatori_2021_sezioni.xlsx", xlsx.getvalue())
    return buffer.getvalue()


def test_census_sections_follow_the_hub_contract(tmp_path: Path) -> None:
    shapes, population = shapes_zip(tmp_path), population_zip()

    def fetch(request: HttpRequest) -> bytes:
        return population if "esploradati" in request.url else shapes

    entry = ingest_layer(LAYER, CATALOG, fetch, tmp_path / "out", NOW)
    assert entry["status"] == "ok", entry.get("error")
    assert entry["features"] == 3  # the non-Rome section is filtered out
    assert set(entry["raw_sha256"]) == {"shapes", "population"}

    data = json.loads((tmp_path / "out" / "census_sections.geojson").read_text(encoding="utf-8"))
    rows = {f["properties"]["sez_id"]: f["properties"] for f in data["features"]}
    assert set(next(iter(rows.values()))) == {"sez_id", "residents", "children_0_14", "municipio", "zone"}
    assert rows["580911010002"] == {"sez_id": "580911010002", "residents": 84, "children_0_14": 7,
                                    "municipio": 1, "zone": "1A"}
    # A section missing from the population table has nobody living in it.
    assert rows["580911010003"]["residents"] == 0 and rows["580911010003"]["children_0_14"] == 0
    assert rows["580911010003"]["municipio"] == 15 and rows["580911010003"]["zone"] == "10A"
    lon, lat = data["features"][0]["geometry"]["coordinates"][0][0]
    assert 12.0 < lon < 13.0 and 41.0 < lat < 42.5  # reprojected from UTM 32N to WGS84
