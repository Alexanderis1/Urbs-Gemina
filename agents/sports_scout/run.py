"""Run the sports scout for one municipio and save the raw result for the pipeline.

    EXA_API_KEY=... python agents/sports_scout/run.py municipio:7 [--effort low]

Writes data/raw/sports_web/scout_<municipio>.json. Nothing is trusted yet:
twin.modules.sports.web_fields validates it when the pipeline builds the layer.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from exa_agent import run_agent, structured  # type: ignore[import-not-found]  # noqa: E402

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("area", help='shared area id, e.g. "municipio:7"')
    parser.add_argument("--effort", default="low")
    args = parser.parse_args()
    kind, _, n = args.area.partition(":")
    if kind != "municipio" or not n.isdigit() or not 1 <= int(n) <= 15:
        parser.error('area must be "municipio:<1-15>"')
    args.municipio = ROMAN[int(n) - 1]
    prompt = (HERE / "prompt.md").read_text(encoding="utf-8").replace("{municipio}", args.municipio)
    schema = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
    run = run_agent(f"Places to play sport in Municipio {args.municipio} of Roma Capitale, Italy",
                    schema, prompt, effort=args.effort)
    out = ROOT / "data" / "raw" / "sports_web"
    out.mkdir(parents=True, exist_ok=True)
    payload = {"agent": "sports_scout", "municipio": args.municipio, "run_id": run["id"],
               "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
               "cost_dollars": run.get("costDollars"), **structured(run)}
    path = out / f"scout_{args.municipio}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(payload.get('candidates', []))} candidates -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
