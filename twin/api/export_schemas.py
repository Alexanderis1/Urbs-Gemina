"""Write the published JSON schemas of every tool to ``twin/api/schemas``.

Run after changing a request model:  python -m twin.api.export_schemas
Other workstreams (agents, Lovable edge functions, voice) read these files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from twin.api.models import EnvelopeOut
from twin.api.tools import TOOLS, tool_schema

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def build_schemas() -> dict[str, dict[str, Any]]:
    files = {f"{name}.json": tool_schema(spec) for name, spec in TOOLS.items()}
    files["envelope.json"] = EnvelopeOut.model_json_schema()
    return files


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for filename, content in build_schemas().items():
        (SCHEMA_DIR / filename).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {SCHEMA_DIR.name}/{filename}")


if __name__ == "__main__":
    main()
