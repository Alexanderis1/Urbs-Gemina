"""Server side of the ElevenLabs ``ask_twin`` webhook tool.

Framework-free: the tool API (or an edge function) mounts ``handle_ask_twin`` at
``POST /voice/ask_twin`` and passes the JSON body and the request headers.

Security model
- Each ElevenLabs agent (office, citizen) sends its own secret in the
  ``X-Urbs-Voice-Secret`` header (stored as an ElevenLabs workspace secret).
- The secret decides the tier. The model cannot pick or raise its tier.
- The office agent is private: the web app gets a signed conversation URL only
  for logged-in office users, so the public cannot talk to it.
"""
from __future__ import annotations

import hmac
import logging
import os
import re
from typing import Any, Mapping

from .briefing import build_briefing
from .contract import LANGUAGES, Language, Orchestrator, Tier, TwinQuestion
from .speech import error_speech, to_speech

log = logging.getLogger(__name__)

SECRET_HEADER = "x-urbs-voice-secret"
CONVERSATION_HEADER = "x-conversation-id"
MAX_QUESTION_CHARS = 500
#: "city", a municipio or urban-zone id. Polygons are not dictated by voice.
AREA_PATTERN = re.compile(r"^[A-Za-z0-9 :_.'\-]{1,64}$")


def secrets_from_env(env: Mapping[str, str] | None = None) -> dict[str, Tier]:
    env = os.environ if env is None else env
    table: dict[str, Tier] = {}
    if env.get("VOICE_SECRET_OFFICE"):
        table[env["VOICE_SECRET_OFFICE"]] = "office"
    if env.get("VOICE_SECRET_CITIZEN"):
        table[env["VOICE_SECRET_CITIZEN"]] = "citizen"
    return table


def _tier_for(secret: str | None, secrets: Mapping[str, Tier]) -> Tier | None:
    if not secret:
        return None
    for known, tier in secrets.items():
        if hmac.compare_digest(secret.encode(), known.encode()):
            return tier
    return None


class BadRequest(ValueError):
    pass


def _parse(body: Mapping[str, Any]) -> tuple[str, Language, str | None, str]:
    params = body.get("parameters") if isinstance(body.get("parameters"), Mapping) else body
    assert isinstance(params, Mapping)
    question = params.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise BadRequest("question must be 1-500 characters")
    language = params.get("language", "it")
    if language not in LANGUAGES:
        raise BadRequest("language must be it or en")
    area = params.get("area")
    if area in ("", None):
        area = None
    elif not isinstance(area, str) or not AREA_PATTERN.match(area):
        raise BadRequest("area must be 'city', a municipio or an urban-zone id")
    mode = params.get("mode", "question")
    if mode not in ("question", "briefing"):
        raise BadRequest("mode must be question or briefing")
    return question.strip(), language, area, mode


def handle_ask_twin(
    body: Mapping[str, Any],
    headers: Mapping[str, str],
    orchestrator: Orchestrator,
    secrets: Mapping[str, Tier],
) -> tuple[int, dict[str, Any]]:
    """Return (HTTP status, JSON body) for one webhook call."""
    lower = {k.lower(): v for k, v in headers.items()}
    tier = _tier_for(lower.get(SECRET_HEADER), secrets)
    if tier is None:
        return 401, {"error": "unauthorised"}
    try:
        question, language, area, mode = _parse(body)
    except BadRequest as exc:
        return 400, {"error": str(exc)}
    conversation_id = lower.get(CONVERSATION_HEADER)

    if mode == "briefing" and tier != "office":
        return 200, error_speech(language, "briefing_citizen_refused")
    try:
        if mode == "briefing":
            answer = build_briefing(orchestrator, area=area or "city", tier=tier, language=language, conversation_id=conversation_id)
        else:
            answer = orchestrator.ask(
                TwinQuestion(question=question, tier=tier, language=language, area=area, mode="question", conversation_id=conversation_id)
            )
    except Exception:  # the caller hears a fixed sentence, never a stack trace
        log.exception("orchestrator failed for conversation %s", conversation_id)
        return 200, error_speech(language)
    return 200, to_speech(answer, language)
