# Tool API (WS4)

FastAPI app exposing the deterministic tools. Every response is the shared tool envelope (`run_id`, `tool`, `status`, `inputs`, `result`, `data_kinds`, `sources`, `synthetic`, `warnings`, `cached`, plus `reason` when `status` is not `ok`).

| Endpoint | What |
|---|---|
| `POST /tools/<name>` | Run a tool. Body = the tool's input schema |
| `GET /tools` | All tool definitions (name, description, input schema) ready for LLM tool calling |
| `GET /tools/<name>/schema` | One tool definition |
| `POST /reports/permit.md` | The cited permit report as Markdown (same body as `permit_report`) |
| `GET /health`, `GET /whoami`, `GET /docs` | Health, your role tier, interactive docs |

Tools: `resolve_place`, `context_check`, `estimate_field`, `query_layer`, `run_scenario` (WS6 engine), `legal_lookup` and `find_dataset` (WS7 `agents.exa_tools`), `data_status`, `permit_report`. A tool whose module is not installed answers `status: "not_available"` with the reason.

Published schemas: `twin/api/schemas/*.json` (regenerate with `python -m twin.api.export_schemas`; a test fails when they are stale). Points are `[lon, lat]`; areas follow `twin/tools/area.py`.

**Role tiers.** `URBS_API_KEYS="key1:office,key2:citizen"`. `Authorization: Bearer <key>`. No key or an unknown key = citizen: no raw feature properties in context checks, aggregated counts for layers in `config/tools.yaml` `api.office_only_detail_layers`.

Run locally: `pip install -e ".[api]"` then `uvicorn twin.api.app:app --reload` and open http://localhost:8000/docs. Hosting: `deploy/README.md`.
