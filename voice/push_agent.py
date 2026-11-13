"""Create or update the ElevenLabs agents (and their webhook secrets) from voice/agents.yaml.

    python -m voice.push_agent --role office --dry-run   # print the payload, no network
    python -m voice.push_agent --role office             # create, or update the agent with the same name
    python -m voice.push_agent --set-secrets             # store VOICE_SECRET_OFFICE / _CITIZEN in ElevenLabs

Environment: ELEVENLABS_API_KEY, VOICE_WEBHOOK_URL (public URL of POST /voice/ask_twin),
optional ELEVENLABS_VOICE_ID. Run --set-secrets whenever the tool API's VOICE_SECRET_* values
change, so the two sides match. The secret values never leave the environment or ElevenLabs.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.request
from typing import Any

from .agent_spec import build_agent_payload

API = "https://api.elevenlabs.io/v1/convai"
PLACEHOLDER_URL = "https://urbs-gemina.invalid/voice/ask_twin"


def secret_name(role: str) -> str:
    return f"urbs_gemina_voice_{role}"


def _call(method: str, path: str, body: Any | None = None) -> Any:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    req = urllib.request.Request(
        f"{API}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else {}


def _secret_ids() -> dict[str, str]:
    return {s["name"]: s["secret_id"] for s in _call("GET", "/secrets").get("secrets", [])}


def ensure_secret(role: str, value: str | None) -> str:
    """Return the secret id for a role, creating it (or updating its value when given)."""
    name = secret_name(role)
    existing = _secret_ids().get(name)
    if existing and value:
        _call("PATCH", f"/secrets/{existing}", {"type": "update", "name": name, "value": value})
    if existing:
        return existing
    # No value yet: a random placeholder; --set-secrets replaces it with the tool API's value.
    created = _call("POST", "/secrets", {"type": "new", "name": name, "value": value or secrets.token_urlsafe(32)})
    return str(created["secret_id"])


def _agent_id_by_name(name: str) -> str | None:
    for agent in _call("GET", "/agents?page_size=100").get("agents", []):
        if agent.get("name") == name:
            return str(agent["agent_id"])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", choices=["office", "citizen"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--set-secrets", action="store_true")
    args = parser.parse_args(argv)

    if args.set_secrets:
        for role in ("office", "citizen"):
            value = os.environ.get(f"VOICE_SECRET_{role.upper()}")
            if not value:
                print(f"VOICE_SECRET_{role.upper()} not set, skipped", file=sys.stderr)
                continue
            print(role, ensure_secret(role, value))
        return 0
    if not args.role:
        parser.error("--role is required")

    url = os.environ.get("VOICE_WEBHOOK_URL", PLACEHOLDER_URL)
    secret_id = "DRY-RUN" if args.dry_run else ensure_secret(args.role, None)
    payload = build_agent_payload(args.role, webhook_url=url, secret_id=secret_id, voice_id=os.environ.get("ELEVENLABS_VOICE_ID"))
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    agent_id = _agent_id_by_name(payload["name"])
    if agent_id:
        _call("PATCH", f"/agents/{agent_id}", payload)
        print(f"updated {args.role} agent {agent_id} (webhook {url})")
    else:
        agent_id = str(_call("POST", "/agents/create", payload)["agent_id"])
        print(f"created {args.role} agent {agent_id} (webhook {url})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
