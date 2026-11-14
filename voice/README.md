# Voice (ElevenLabs), workstream WS9

Two ElevenLabs voice agents that talk to the same orchestrator and guardrails as the chat.

| Agent | Who | Where | Can do |
|---|---|---|---|
| Office | Logged-in officers | Widget in the Lovable app, private agent (signed URL from an edge function) | Questions, morning briefing per municipio, all map tools |
| Citizen line | Anyone | Public widget (phone number optional later) | Questions on public, aggregated data; no permit circle, no briefing |

## How a spoken question flows

1. The agent opens with an AI disclosure (`agents.yaml`). Italian only (decision of 13 Nov 2026); English texts stay in the files so it can be switched on later.
2. For any question about Rome it calls the one webhook tool `ask_twin` (question, optional area, language, mode).
3. `webhook.handle_ask_twin` checks the per-agent secret header. **The secret decides the tier** (office or citizen); the model cannot choose it.
4. The question goes to the orchestrator (shared interface 7: `agents/contract.py`, re-exported by `voice/contract.py`). Areas use the shared ids `city`, `municipio:<1-15>`, `zone:<CODE>`. The briefing is one question with `mode=briefing`; the orchestrator runs it as the `municipio_briefing` playbook (`config/use_cases.yaml`). `ask_twin` also takes an optional `use_case` and `place` for the other playbooks.
5. `speech.to_speech` turns the answer into speech: unverified answers become "insufficient data" plus what is missing; run ids and links are removed from the spoken text but returned in the payload (shown on screen); simulated data is announced; map moves outside Rome are dropped.
6. The agent reads `speak` and calls the map client tools (`client_tools.json`) with the `map_actions` it received.
7. After the call, `audit.audit_transcript` flags any number the agent said that no tool returned.

## Files

| File | What |
|---|---|
| `contract.py` | `TwinQuestion` / `TwinAnswer` / `Orchestrator`: the hand-over to the agents stream |
| `webhook.py` | `ask_twin` handler (auth, tier, validation, briefing, errors) |
| `speech.py`, `phrases.yaml` | Answer to speech, fixed sentences in it / en |
| `briefing.py` | Morning briefing per municipio (one playbook call) |
| `agents.yaml`, `prompts/*.md`, `agent_spec.py` | The two agent definitions; the shared answer contract is pasted into each prompt |
| `client_tools.json` | Map tools shared with the web app |
| `audit.py` | Post-call number audit |
| `push_agent.py` | Create / update the agents through the ElevenLabs API |

## Setup

```bash
python -m voice.push_agent --role office --dry-run   # look at the payload
export ELEVENLABS_API_KEY=... VOICE_WEBHOOK_URL=https://<tool-api>/voice/ask_twin
export ELEVENLABS_SECRET_ID_OFFICE=... ELEVENLABS_SECRET_ID_CITIZEN=... ELEVENLABS_VOICE_ID=...
python -m voice.push_agent --role office
python -m voice.push_agent --role citizen
```

The tool API needs `VOICE_SECRET_OFFICE` and `VOICE_SECRET_CITIZEN` (same values as the ElevenLabs workspace secrets) and mounts `handle_ask_twin(body, headers, orchestrator, secrets_from_env())` at `POST /voice/ask_twin`.

## Where the keys live (never in git, never in chat)

| Key | Stored in | Used by |
|---|---|---|
| `ELEVENLABS_API_KEY` | Lovable Cloud Secrets | Edge function that asks ElevenLabs for a signed URL for the private office agent |
| `ELEVENLABS_API_KEY` | Your own shell (or this project's cloud environment variables) when running `push_agent` | Creating / updating the agents |
| `VOICE_SECRET_OFFICE`, `VOICE_SECRET_CITIZEN` | Tool API host secrets (e.g. Modal secret) **and** ElevenLabs workspace secrets | Checking who calls `ask_twin` |

The webhook itself does not need the ElevenLabs key.

## Live agents (created 13 Nov 2026)

| Agent | ElevenLabs id | Access |
|---|---|---|
| Office | `agent_5801m7b8bx9gedj9fj7r1e3s54vh` | Private: the web app asks for a signed URL (`GET /v1/convai/conversation/get-signed-url?agent_id=...`) from an edge function |
| Citizen line | `agent_1501m7b8c0zpfxm9r3wq8cg1sz9b` | Public: the widget can use the id directly |

Both use `claude-haiku-5-5`, the Italian voice "Fabi" (`Ha21jUwaMwdgQvqNslSM`) and `eleven_flash_v2_5`; ElevenLabs accepted all three. The webhook URL is still a placeholder: once the tool API is deployed, run

```bash
VOICE_WEBHOOK_URL=https://<tool-api>/voice/ask_twin python -m voice.push_agent --role office
VOICE_WEBHOOK_URL=https://<tool-api>/voice/ask_twin python -m voice.push_agent --role citizen
VOICE_SECRET_OFFICE=... VOICE_SECRET_CITIZEN=... python -m voice.push_agent --set-secrets   # same values as the tool API
```

## Not verified yet

- Whether ElevenLabs sends the body flat or wrapped in `parameters`: the handler accepts both.
