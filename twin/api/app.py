"""FastAPI tool API: ``POST /tools/<name>`` for every deterministic tool.

Run locally:  uvicorn twin.api.app:app --reload

Role tiers are enforced here, not in prompts. ``URBS_API_KEYS`` holds
``key:role`` pairs separated by commas; a request without a known
``Authorization: Bearer <key>`` is served at the citizen tier.
"""
import dataclasses
import hmac
import importlib
import logging
import os
import threading
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from twin.api.jobs import Jobs, modal_store
from twin.api.models import AskIn, EnvelopeOut
from twin.api.orchestrator import TierOrchestrator
from twin.api.tools import TOOLS, ToolSpec, tool_schema
from twin.tools.envelope import ToolError
from twin.tools.runtime import ToolRuntime

log = logging.getLogger("urbs.api")
ROLES = ("citizen", "office")


def parse_keys(raw: str | None) -> dict[str, str]:
    keys: dict[str, str] = {}
    for pair in (raw or "").split(","):
        if ":" not in pair:
            continue
        key, role = pair.rsplit(":", 1)
        if key.strip() and role.strip() in ROLES:
            keys[key.strip()] = role.strip()
    return keys


def create_app(runtime: ToolRuntime | None = None, api_keys: dict[str, str] | None = None) -> FastAPI:
    keys = parse_keys(os.environ.get("URBS_API_KEYS")) if api_keys is None else api_keys
    app = FastAPI(
        title="Urbs Gemina tool API",
        version="0.1.0",
        description="Deterministic tools of the Rome digital twin. Every response is a tool envelope with a "
                    "run id, sources and real / estimated / simulated labels. Decision support only.",
    )
    @app.middleware("http")
    async def json_errors(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Unexpected errors become JSON inside the CORS layer, so browsers see the error, not a CORS failure."""
        try:
            return await call_next(request)
        except Exception as error:  # noqa: BLE001 - last resort; the traceback goes to the server log
            log.exception("unhandled error on %s", request.url.path)
            return JSONResponse(status_code=500, content={"error": f"{type(error).__name__}: {error}",
                                                          "path": request.url.path})

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])
    store_name = os.environ.get("URBS_JOBS_DICT", "")
    jobs = Jobs(float(os.environ.get("URBS_SYNC_WAIT_S", "0")), modal_store(store_name) if store_name else None)

    def answer(fn: Callable[[], Any]) -> Any:
        """The result, or a 202 with a job id when the work outlasts URBS_SYNC_WAIT_S (see twin/api/jobs.py)."""
        finished, value = jobs.run(fn)
        if finished:
            return value
        return JSONResponse(status_code=202, content={"status": "running", "job_id": value, "poll": f"/jobs/{value}"})

    state: dict[str, ToolRuntime] = {}
    state_lock = threading.Lock()

    def get_runtime() -> ToolRuntime:
        if "rt" not in state:
            with state_lock:  # warm-up and the first requests must share one runtime, not build several
                if "rt" not in state:
                    state["rt"] = runtime or ToolRuntime.default()
        return state["rt"]

    def get_role(authorization: str | None = Header(default=None)) -> str:
        if authorization and authorization.lower().startswith("bearer "):
            given = authorization[7:].strip()
            for key, role in keys.items():
                if hmac.compare_digest(given.encode(), key.encode()):
                    return role
        return "citizen"

    @app.on_event("startup")
    def warm_up() -> None:
        """Build the runtime and preload slow providers in the background, so the first request is fast."""
        if os.environ.get("URBS_WARMUP", "1") == "0":
            return

        def run() -> None:
            try:
                log.info("warm-up: %s", get_runtime().warm())
            except Exception:  # noqa: BLE001 - best effort
                log.exception("warm-up failed")

        threading.Thread(target=run, name="urbs-warmup", daemon=True).start()

    @app.exception_handler(ToolError)
    async def tool_error(request: Request, error: ToolError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(error), "path": request.url.path})

    @app.get("/")
    def index() -> dict[str, Any]:
        return {"name": "Urbs Gemina tool API", "docs": "/docs", "tools": sorted(TOOLS),
                "notice": "Decision support only. Numbers come from deterministic tools."}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    def whoami(role: str = Depends(get_role)) -> dict[str, str]:
        return {"role": role}

    @app.get("/tools")
    def list_tools() -> list[dict[str, Any]]:
        return [tool_schema(spec) for spec in TOOLS.values()]

    @app.get("/tools/{name}/schema")
    def schema(name: str) -> dict[str, Any]:
        if name not in TOOLS:
            raise HTTPException(status_code=404, detail=f"unknown tool '{name}'")
        return tool_schema(TOOLS[name])

    def register(spec: ToolSpec) -> None:
        model: type[BaseModel] = spec.model

        def endpoint(body: model | None = None,  # type: ignore[valid-type]
                     role: str = Depends(get_role),
                     rt: ToolRuntime = Depends(get_runtime)) -> dict[str, Any]:
            request = body if body is not None else model()

            def work() -> dict[str, Any]:
                envelope: dict[str, Any] = spec.handler(rt, request, role)
                log.info("tool=%s run=%s role=%s", spec.name, str(envelope["run_id"])[:12], role)
                return envelope

            return answer(work)  # type: ignore[no-any-return]

        app.post(f"/tools/{spec.name}", response_model=EnvelopeOut, response_model_exclude_unset=True,
                 summary=spec.description,
                 name=spec.name)(endpoint)

    for spec in TOOLS.values():
        register(spec)

    @app.post("/reports/permit.md", response_class=PlainTextResponse)
    def permit_markdown(body: TOOLS["permit_report"].model,  # type: ignore[valid-type]
                        role: str = Depends(get_role),
                        rt: ToolRuntime = Depends(get_runtime)) -> str:
        envelope = TOOLS["permit_report"].handler(rt, body, role)
        markdown: str = envelope["result"]["markdown"]
        return markdown

    orchestrators: dict[str, Any] = {}

    def get_orchestrator() -> Any:
        if "o" not in orchestrators:
            try:
                orchestrators["o"] = TierOrchestrator(get_runtime)
            except ImportError as error:
                raise HTTPException(status_code=501, detail=f"orchestrator (WS7 agents) not installed: {error}")
        return orchestrators["o"]

    @app.post("/ask")
    def ask(body: AskIn, role: str = Depends(get_role)) -> dict[str, Any]:
        """Chat entry point (shared interface 7). The tier comes from the API key, never from the body."""
        contract = importlib.import_module("agents.contract")
        question = contract.TwinQuestion(question=body.question, tier=role, language=body.language, area=body.area,
                                         mode=body.mode, conversation_id=body.conversation_id, channel="chat",
                                         use_case=body.use_case, params=dict(body.params))
        orchestrator = get_orchestrator()
        return answer(lambda: dataclasses.asdict(orchestrator.ask(question)))  # type: ignore[no-any-return]

    @app.get("/jobs/{job_id}")
    def job(job_id: str) -> JSONResponse:
        """Poll a long request that answered 202. ``status`` is running, done (with ``result``) or error."""
        found = jobs.get(job_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"unknown job '{job_id}'")
        return JSONResponse(status_code=200, content=found)

    @app.get("/use_cases")
    def use_cases(role: str = Depends(get_role)) -> list[dict[str, Any]]:
        """Ready-made playbooks this caller's tier may run (send the id as ``use_case`` to POST /ask)."""
        try:
            uc_mod = importlib.import_module("agents.use_cases")
        except ImportError as error:
            raise HTTPException(status_code=501, detail=f"use cases (WS7 agents) not installed: {error}")
        return [{"id": uc.id, "title": dict(uc.title), "summary": dict(uc.summary), "needs": list(uc.needs),
                 "params": {k: v.get("default") for k, v in uc.params.items()},
                 "steps": [s.label for s in uc.steps]}
                for uc in uc_mod.load_use_cases().values() if role in uc.tiers]

    @app.post("/voice/ask_twin")
    async def voice_ask_twin(request: Request) -> JSONResponse:
        """ElevenLabs webhook (WS9). The per-agent secret header decides the tier."""
        try:
            webhook = importlib.import_module("voice.webhook")
        except ImportError as error:
            return JSONResponse(status_code=501, content={"error": f"voice webhook (WS9) not installed: {error}"})
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "body must be JSON"})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"error": "body must be a JSON object"})
        status, payload = webhook.handle_ask_twin(body, dict(request.headers), get_orchestrator(),
                                                  webhook.secrets_from_env())
        return JSONResponse(status_code=int(status), content=payload)

    return app


app = create_app()
