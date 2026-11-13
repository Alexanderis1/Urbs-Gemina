# Agents (WS7)

Numbers come from tools, words come from the model, and code checks the join.

| File | What it does |
|---|---|
| `orchestrator.py` | Answers a question with tools, runs the verifier, rewrites once, otherwise says "insufficient data". `TwinOrchestrator.ask(TwinQuestion) -> TwinAnswer` is shared interface 7, used by chat (WS8) and voice (WS9). |
| `permit.py` | Challenge 02 flow. Code calls `resolve_place` → `context_check` (radius from `config/thresholds.yaml`) → `estimate_field` (on the circle) → `legal_lookup`; the model only writes the narrative, which is verified. `report_json` hands the runs to the WS4 report builder. |
| `scenario.py` | Asks for kind, area and change before `run_scenario`; explains the delta from the tool output only. |
| `steward.py` | Exa monitors (roadworks, strikes, demonstrations, new datasets). `scan` reads and writes nothing; `propose` is an officer action that queues an ingest for approval. |
| `verifier.py` | The deterministic check behind guardrails 1, 3, 6 and 7. |
| `exa_tools.py` | `legal_lookup`, `find_dataset`, `news_search`: Exa restricted to official domains, re-filtered in code. |
| `loop.py` | Model → tools → model loop with the turn guard (no state change after web content). |
| `web.py` | Domain check, injection scan, quote fence. |
| `tools.py` | Tool specs and gateways (`POST /tools/<name>` on the tool API; local Exa tools). Uses `twin/api/schemas/*.json` when WS4 publishes them, `tool_schemas_draft.json` until then. |
| `llm.py` | Claude via the official SDK (model per agent in `config/agents.yaml`: Opus 5.5, Sonnet 5.5 for voice). |
| `contract.py` | `TwinQuestion` / `TwinAnswer` (shared interface 7). |
| `prompts/` | `answer_contract.md` (shared), `citations.md`, one prompt per agent. |

## Run

```bash
pip install -e ".[dev,agents]"
export ANTHROPIC_API_KEY=...  EXA_API_KEY=...  URBS_TOOL_API_URL=https://...
python -m eval.run_eval          # offline, no cost
python -m eval.run_eval --live   # real model on the same fixtures
```

Settings and every assumption with its `basis:` note: `config/agents.yaml`.
