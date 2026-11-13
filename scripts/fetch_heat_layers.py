"""Static layers for the heatwave scenario (WS6), written to the shared processed folder.

* ``tree_cover_2018.tif``: Copernicus HRL Tree Cover Density 2018 (0-100 %, 255 = no data), on the same
  20 m EPSG:3035 grid as ``imperviousness_2018.tif``. EEA image service, no key, free and open.
* ``census_ages.csv``: residents aged 65+ and 75+ per ISTAT 2021 census section (P27+P28+P29 and P29),
  same ``sez_id`` as ``census_sections.geojson``. ISTAT, CC BY 4.0. Aggregates only, no personal data.

Usage: python scripts/fetch_heat_layers.py [tree_cover] [census_ages] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping

TREE_COVER_SERVICE = ("https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/"
                      "HRL_TreeCoverDensity_2018/ImageServer/exportImage")
ISTAT_SECTIONS_ZIP = "https://esploradati.istat.it/databrowser/DWL/PERMPOP/SUBCOM/Comuni_2021.zip"
ISTAT_MEMBER = "Roma_indicatori_2021_sezioni.xlsx"
DEFAULT_OUT = Path("/mnt/project-files/data/processed")


def tree_cover_url(bounds: tuple[float, float, float, float], size: tuple[int, int]) -> str:
    left, bottom, right, top = (f"{v:.0f}" for v in bounds)
    return (f"{TREE_COVER_SERVICE}?bbox={left},{bottom},{right},{top}&bboxSR=3035&imageSR=3035"
            f"&size={size[0]},{size[1]}&format=tiff&pixelType=U8&interpolation=RSP_NearestNeighbor&f=image")


def _int(v: Any) -> int:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0
    return int(v)


def ages_rows(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, int, int]]:
    """(sez_id, residents 65+, residents 75+) from ISTAT 2021 section rows."""
    return [(str(int(float(r["SEZ21_ID"]))), _int(r.get("P27")) + _int(r.get("P28")) + _int(r.get("P29")),
             _int(r.get("P29"))) for r in rows]


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=600) as resp:  # noqa: S310 - fixed public https URLs
        data: bytes = resp.read()
    return data


def fetch_tree_cover(out_dir: Path) -> Path:
    import numpy as np
    import rasterio  # type: ignore[import-untyped]

    template = out_dir / "imperviousness_2018.tif"
    with rasterio.open(template) as t:
        bounds = (t.bounds.left, t.bounds.bottom, t.bounds.right, t.bounds.top)
        size = (t.width, t.height)
        profile = t.profile.copy()
    raw = _get(tree_cover_url(bounds, size))
    with rasterio.io.MemoryFile(raw) as mem, mem.open() as src:
        band = src.read(1)
    band = np.where(band > 100, 255, band).astype("uint8")
    profile.update(dtype="uint8", nodata=255, compress="deflate", count=1)
    out = out_dir / "tree_cover_2018.tif"
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(band, 1)
    return out


def fetch_census_ages(out_dir: Path) -> Path:
    import pandas as pd  # type: ignore[import-untyped,import-not-found,unused-ignore]

    with zipfile.ZipFile(io.BytesIO(_get(ISTAT_SECTIONS_ZIP))) as archive:
        workbook = archive.read(ISTAT_MEMBER)
    table = pd.read_excel(io.BytesIO(workbook), sheet_name=0, usecols=["SEZ21_ID", "P27", "P28", "P29"])
    out = out_dir / "census_ages.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["sez_id", "elderly_65_plus", "elderly_75_plus"])
        writer.writerows(ages_rows(table.to_dict("records")))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("layers", nargs="*", default=["tree_cover", "census_ages"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    for layer in args.layers:
        path = {"tree_cover": fetch_tree_cover, "census_ages": fetch_census_ages}[layer](args.out)
        print(f"{layer}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
