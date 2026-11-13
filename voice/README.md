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
4. The question goes to the orchestrator (`contract.Orchestrator`, built by the agents stream). The briefing is a fixed list of questions in `briefing.yaml`, each sent to the orchestrator too.
5. `speech.to_speech` turns the answer into speech: unverified answers become "insufficient data" plus what is missing; run ids and links are removed from the spoken text but returned in the payload (shown on screen); simulated data is announced; map moves outside Rome are dropped.
6. The agent reads `speak` and calls the map client tools (`client_tools.json`) with the `map_actions` it received.
7. After the call, `audit.audit_transcript` flags any number the agent said that no tool returned.

## Files

| File | What |
|---|---|
| `contract.py` | `TwinQuestion` / `TwinAnswer` / `Orchestrator`: the hand-over to the agents stream |
| `webhook.py` | `ask_twin` handler (auth, tier, validation, briefing, errors) |
| `speech.py`, `phrases.yaml` | Answer to speech, fixed sentences in it / en |
| `briefing.py`, `briefing.yaml` | Morning briefing per municipio |
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

## Not verified yet

- Exact ElevenLabs LLM id (`claude-haiku-4-5`) and TTS id (`eleven_flash_v2_5`), C=60-70. A dry run plus one push will confirm.
- Whether ElevenLabs sends the body flat or wrapped in `parameters`: the handler accepts both.
