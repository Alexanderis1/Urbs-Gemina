"""Run the sports scout for one municipio and save the raw result for the pipeline.

    EXA_API_KEY=... python agents/sports_scout/run.py VII [--effort low]

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

from exa_agent import run_agent, structured  # noqa: E402

ROMAN = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("municipio", help="Roman numeral, e.g. VII")
    parser.add_argument("--effort", default="low")
    args = parser.parse_args()
    if args.municipio not in ROMAN:
        parser.error("municipio must be a Roman numeral I-XV")
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
