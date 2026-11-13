"""Create or update an ElevenLabs agent from voice/agents.yaml.

    python -m voice.push_agent --role office --dry-run          # print the payload
    python -m voice.push_agent --role office                    # create
    python -m voice.push_agent --role office --agent-id agent_x # update

Environment: ELEVENLABS_API_KEY, VOICE_WEBHOOK_URL (public URL of POST /voice/ask_twin),
ELEVENLABS_SECRET_ID_OFFICE / ELEVENLABS_SECRET_ID_CITIZEN (workspace secrets that hold
VOICE_SECRET_OFFICE / VOICE_SECRET_CITIZEN), optional ELEVENLABS_VOICE_ID.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from .agent_spec import build_agent_payload

API = "https://api.elevenlabs.io/v1/convai/agents"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=["office", "citizen"], required=True)
    parser.add_argument("--agent-id", help="update this agent instead of creating one")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = build_agent_payload(
        args.role,
        webhook_url=os.environ.get("VOICE_WEBHOOK_URL", "https://REPLACE-ME/voice/ask_twin"),
        secret_id=os.environ.get(f"ELEVENLABS_SECRET_ID_{args.role.upper()}", "REPLACE-ME"),
        voice_id=os.environ.get("ELEVENLABS_VOICE_ID"),
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY is not set", file=sys.stderr)
        return 2
    url, method = (f"{API}/{args.agent_id}", "PATCH") if args.agent_id else (f"{API}/create", "POST")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method=method,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        print(resp.read().decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
