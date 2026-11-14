"""Download Regione Lazio daily rain and temperature for the Rome gauges (Sep 2018 onwards).

    python scripts/fetch_lazio_gauges.py [--out /mnt/project-files/data/processed/lazio_gauges]

Writes rain_daily.csv (station, lon, lat, day, mm) and temperature_daily.csv
(station, lon, lat, day, t_min, t_max), plus stations.json listing what matched.
Source and licence: twin/providers/open/lazio_gauges.py (CC BY 4.0).
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from twin.providers import http
from twin.providers.open import lazio_gauges as lg


def resource_urls(dataset: str) -> list[str]:
    meta = json.loads(http.get_bytes(lg.CKAN + dataset, timeout_s=60.0).decode("utf-8"))
    return [r["url"] for r in meta["result"]["resources"] if str(r.get("format", "")).upper() == "CSV"]


def download(url: str, attempts: int = 4) -> str:
    """The portal answers HTTP 500 at random under load: retry with a pause before giving up."""
    raw = b""
    for attempt in range(attempts):
        try:
            raw = http.get_bytes(url, timeout_s=120.0)
            break
        except Exception as exc:  # noqa: BLE001 - one broken month must not stop the rest
            if attempt == attempts - 1:
                print(f"skip {url}: {exc}")
                return ""
            time.sleep(3.0 * (attempt + 1))
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/mnt/project-files/data/processed/lazio_gauges")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gauges = lg.load_gauges()
    seen: dict[str, set[str]] = {"rain": set(), "temperature": set()}
    unavailable: list[str] = []
    for kind, dataset in lg.DATASETS.items():
        urls = resource_urls(dataset)
        with ThreadPoolExecutor(max_workers=3) as pool:
            texts = list(pool.map(download, urls))
        parse = lg.parse_rain if kind == "rain" else lg.parse_temperature
        records = []
        for url, text in zip(urls, texts):
            if text and not text.lstrip().startswith("<"):
                records.extend(lg.in_rome(parse(text), gauges))
            else:  # the portal serves an HTML error page for some months
                unavailable.append(url.rsplit("/", 1)[-1])
        path = out / f"{kind}_daily.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if kind == "rain":
                w.writerow(["station", "lon", "lat", "day", "mm"])
            else:
                w.writerow(["station", "lon", "lat", "day", "t_min", "t_max"])
            for r in sorted(records, key=lambda r: (lg.norm(r.station), r.day)):
                g = gauges[lg.norm(r.station)]
                seen[kind].add(g.name)
                if isinstance(r, lg.DailyRain):
                    w.writerow([g.name, g.lon, g.lat, r.day.isoformat(), r.mm])
                else:
                    w.writerow([g.name, g.lon, g.lat, r.day.isoformat(),
                                "" if r.t_min is None else r.t_min, "" if r.t_max is None else r.t_max])
        print(f"{kind}: {len(urls)} monthly files, {len(records)} Rome readings, {len(seen[kind])} stations -> {path}")
    unmatched = sorted(g.name for g in gauges.values() if g.name not in seen["rain"] | seen["temperature"])
    (out / "stations.json").write_text(json.dumps({
        "licence": lg.LICENCE, "positions": "Roma Capitale Civil Protection plan, Fascicolo 1 (Dec 2018), Tab. 8",
        "rain_stations": sorted(seen["rain"]), "temperature_stations": sorted(seen["temperature"]),
        "in_register_but_not_in_files": unmatched,
        "files_unavailable_on_portal": sorted(unavailable)}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
