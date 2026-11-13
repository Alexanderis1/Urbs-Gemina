"""Enrich merged facilities with web-sourced fields.

    EXA_API_KEY=... python agents/sports_enrich/run.py --municipio VII [--effort medium] [--batch 25]

Reads data/processed/sports/facilities.geojson (built by
``python -m twin.modules.sports.pipeline build``), sends facilities in batches
as Exa Agent input rows, writes one data/raw/sports_web/enrich_<facility_id>.json
per facility. The pipeline validates them on the next build.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "sports_scout"))

from exa_agent import run_agent, structured  # type: ignore[import-not-found]  # noqa: E402


def rows(municipio: str | None) -> list[dict[str, Any]]:
    layer = json.loads((ROOT / "data" / "processed" / "sports" / "facilities.geojson").read_text(encoding="utf-8"))
    out = []
    for feature in layer["features"]:
        p = feature["properties"]
        if municipio and p.get("municipio") != municipio:
            continue
        out.append({"facility_id": p["facility_id"], "name": p["name"], "kind": p["kind"],
                    "municipio": p.get("municipio"), "address": p["fields"]["address"]["value"],
                    "coordinates": (feature.get("geometry") or {}).get("coordinates")})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--municipio", default=None)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--batch", type=int, default=25)
    args = parser.parse_args()
    prompt = (HERE / "prompt.md").read_text(encoding="utf-8")
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    out = ROOT / "data" / "raw" / "sports_web"
    out.mkdir(parents=True, exist_ok=True)
    todo = rows(args.municipio)
    today = datetime.now(timezone.utc).date().isoformat()
    written = 0
    for start in range(0, len(todo), args.batch):
        batch = todo[start:start + args.batch]
        wanted = {r["facility_id"] for r in batch}
        run = run_agent("Find disciplines, opening hours, accessibility and organisational contacts "
                        "for each of these sports facilities in Rome, Italy", schema, prompt,
                        effort=args.effort, data=batch)
        for item in structured(run).get("facilities", []):
            fid = str(item.get("facility_id", ""))
            if fid not in wanted:
                continue  # the agent must not invent ids
            payload = {"agent": "sports_enrich", "run_id": run["id"], "retrieved_at": today, **item}
            (out / f"enrich_{fid}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
            written += 1
    print(f"{written}/{len(todo)} facilities enriched -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
