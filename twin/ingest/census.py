"""ISTAT 2021 census sections of Roma Capitale with residents and children 0-14.

Inputs (both open, CC BY 4.0):

* the Lazio "basi territoriali 2021" zip: section polygons (UTM 32N) and the
  table that maps each third-level sub-area (COM_ASC3) to its urban-zone code;
* the "Comuni 2021" zip of census results per section: total residents (P1) and
  residents aged 0-4, 5-9 and 10-14 (P14, P15, P16).

Output columns are fixed by the hub contract and nothing else is kept:
``sez_id`` (str), ``residents`` (int), ``children_0_14`` (int),
``municipio`` (int 1-15), ``zone`` (urban-zone code, upper case).
ISTAT lists only sections with residents, so a section missing from the results
table has ``residents = 0``.
"""
from __future__ import annotations

import csv
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from twin.ingest.catalog import LayerSpec

OUTPUT_COLUMNS = ["sez_id", "residents", "children_0_14", "municipio", "zone"]


def _zone_codes(archive: zipfile.ZipFile, member: str) -> dict[int, str]:
    text = archive.read(member).decode("utf-16")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    return {int(row["COM_ASC3"]): row["COD_ASC3_T"].strip().upper() for row in reader}


def _population(raw: bytes, options: dict[str, Any]) -> Any:
    import pandas as pd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        workbook = archive.read(str(options["population_member"]))
    residents = str(options["residents_column"])
    children = [str(c) for c in options["children_columns"]]
    table = pd.read_excel(io.BytesIO(workbook), sheet_name=str(options["population_sheet"]),
                          usecols=["SEZ21_ID", residents, *children])
    return pd.DataFrame({
        "sez_id": table["SEZ21_ID"].astype("int64").astype(str),
        "residents": table[residents].astype("int64"),
        "children_0_14": table[children].sum(axis=1).astype("int64"),
    })


def build_census_sections(layer: LayerSpec, shapes_raw: bytes, population_raw: bytes) -> Any:
    """Return a GeoDataFrame (EPSG:4326) with exactly OUTPUT_COLUMNS plus geometry."""
    import geopandas as gpd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    options = layer.options
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(io.BytesIO(shapes_raw)) as archive:
            zones = _zone_codes(archive, str(options["zones_member"]))
            stem = str(options["shapes_member"])[: -len(".shp")]
            members = [n for n in archive.namelist() if n.startswith(stem + ".")]
            for name in members:
                archive.extract(name, tmp)
        frame = gpd.read_file(Path(tmp) / str(options["shapes_member"]))

    for column, value in layer.filter.items():
        frame = frame[frame[column] == value]

    sections = gpd.GeoDataFrame(
        {
            "sez_id": frame["SEZ21_ID"].astype("int64").astype(str).to_numpy(),
            "municipio": (frame["COM_ASC1"].astype("int64") % 1000).to_numpy(),
            "zone": [zones.get(int(code), "") for code in frame["COM_ASC3"]],
        },
        geometry=frame.geometry.to_numpy(),
        crs=frame.crs,
    ).to_crs("EPSG:4326")

    population = _population(population_raw, options)
    merged = sections.merge(population, on="sez_id", how="left")
    merged["residents"] = merged["residents"].fillna(0).astype("int64")
    merged["children_0_14"] = merged["children_0_14"].fillna(0).astype("int64")
    merged["municipio"] = merged["municipio"].astype("int64")
    return merged[[*OUTPUT_COLUMNS, "geometry"]]
