"""Sport coverage for all 15 municipi: straight-line reach vs real walking network, per discipline.

    python scripts/sports_coverage_all.py [--facilities PATH] [--census PATH] [--out DIR]

Writes coverage_all_municipi.json and .md (aggregates only: residents and children per municipio).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from twin.modules.sports.config import load_config
from twin.modules.sports.deserts import coverage, reach_radius_m, street_budget_m
from twin.modules.sports.network import load_default
from twin.modules.sports.pipeline import load_facilities, load_population

DISCIPLINES = ("football", "tennis", "basketball", "volleyball", "athletics", "padel", "swimming")
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--facilities", default="/mnt/project-files/sports/municipio_VII/facilities.geojson")
    p.add_argument("--census", default="/mnt/project-files/data/processed/census_sections.geojson")
    p.add_argument("--out", default="/mnt/project-files/sports/all_municipi")
    args = p.parse_args()
    t0 = time.time()
    cfg = load_config()
    facilities = load_facilities(Path(args.facilities))
    people = load_population(Path(args.census))
    graph = load_default()
    if graph is None:
        raise SystemExit("walking network missing: run scripts/build_walk_graph.py")
    radius, street = reach_radius_m(cfg), street_budget_m(cfg)
    rows: list[dict[str, Any]] = []
    for d in DISCIPLINES:
        line = coverage(people, facilities, d, radius, True, cfg)
        walk = coverage(people, facilities, d, radius, True, cfg, graph, street)
        by_m_line: dict[str, list[float]] = {}
        by_m_walk: dict[str, list[float]] = {}
        unc_line = set(line["uncovered_points"])
        unc_walk = set(walk["uncovered_points"])
        for pt in people:
            m = pt.municipio or "?"
            for table, unc in ((by_m_line, unc_line), (by_m_walk, unc_walk)):
                agg = table.setdefault(m, [0.0, 0.0, 0.0, 0.0])
                agg[0] += pt.residents
                agg[1] += pt.children
                if pt.point_id in unc:
                    agg[2] += pt.residents
                    agg[3] += pt.children
        for m in ROMAN:
            a, b = by_m_line.get(m), by_m_walk.get(m)
            if a is None or b is None:
                continue
            rows.append({"discipline": d, "municipio": m, "residents": round(a[0]),
                         "uncovered_straight_line": round(a[2]), "uncovered_walking": round(b[2]),
                         "children_uncovered_walking": round(b[3]),
                         "share_uncovered_walking": round(b[2] / a[0], 4) if a[0] else None})
        print(f"{d}: uncovered {line['residents_uncovered']:.0f} (straight line) vs {walk['residents_uncovered']:.0f} "
              f"(walking) of {walk['residents_total']:.0f} ({time.time() - t0:.0f} s)")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "coverage_all_municipi.json").write_text(json.dumps({
        "reach": {"walk_minutes": cfg.reach.walk_minutes, "street_m": street, "straight_line_m": round(radius, 1)},
        "facilities": len(facilities), "population_points": len(people), "rows": rows}, indent=1))
    md = ["# Sport coverage, all 15 municipi", "",
          f"15-minute walk: {street:.0f} m along real streets (Overture walking network) versus the old "
          f"straight-line {radius:.0f} m. Residents from ISTAT 2021 census sections; facilities from the "
          "fused sports layer (official + OSM + web, unverified included). Estimated.", "",
          "| Discipline | Municipio | Residents | Uncovered (straight line) | Uncovered (walking) | Share (walking) |",
          "|---|---|---|---|---|---|"]
    md += [f"| {r['discipline']} | {r['municipio']} | {r['residents']:,} | {r['uncovered_straight_line']:,} | "
           f"{r['uncovered_walking']:,} | {r['share_uncovered_walking']:.0%} |" for r in rows]
    (out / "coverage_all_municipi.md").write_text("\n".join(md) + "\n")
    print(f"wrote {out} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
