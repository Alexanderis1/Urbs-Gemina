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
#: Shared area ids: "city", "municipio:<1-15>", "zone:<CODE>". Polygons are not dictated by voice.
AREA_PATTERN = re.compile(r"^(?:city|municipio:(?:[1-9]|1[0-5])|zone:[A-Za-z0-9_\-]{1,20})$")
#: Playbook ids from config/use_cases.yaml; the orchestrator checks the tier may run it.
USE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,59}$")
MAX_PLACE_CHARS = 200
#: Options the user states aloud, passed to the playbook as given (they are inputs, not results).
#: basis: plausible bounds only to reject mishearings; the playbook defaults live in config/use_cases.yaml.
MAX_ATTENDEES = 2_000_000
TMAX_RANGE_C = (20.0, 55.0)
MAX_DISCIPLINE_CHARS = 40


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


def _parse(body: Mapping[str, Any]) -> tuple[str, Language, str | None, str, str | None, dict[str, Any]]:
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
        raise BadRequest("area must be city, municipio:<1-15> or zone:<CODE>")
    mode = params.get("mode", "question")
    if mode not in ("question", "briefing"):
        raise BadRequest("mode must be question or briefing")
    use_case = params.get("use_case")
    if use_case in ("", None):
        use_case = None
    elif not isinstance(use_case, str) or not USE_CASE_PATTERN.match(use_case):
        raise BadRequest("use_case must be a playbook id such as heat_plan_elderly")
    place = params.get("place")
    extra: dict[str, Any] = {}
    if isinstance(place, str) and place.strip():
        if len(place) > MAX_PLACE_CHARS:
            raise BadRequest("place must be at most 200 characters")
        extra["place"] = place.strip()
    attendees = params.get("attendees")
    if attendees is not None:
        if isinstance(attendees, bool) or not isinstance(attendees, int) or not 1 <= attendees <= MAX_ATTENDEES:
            raise BadRequest("attendees must be a whole number of people")
        extra["attendees"] = attendees
    tmax = params.get("tmax_c")
    if tmax is not None:
        if isinstance(tmax, bool) or not isinstance(tmax, (int, float)) or not TMAX_RANGE_C[0] <= tmax <= TMAX_RANGE_C[1]:
            raise BadRequest("tmax_c must be a temperature between 20 and 55 °C")
        extra["tmax_c"] = tmax
    discipline = params.get("discipline")
    if isinstance(discipline, str) and discipline.strip():
        if len(discipline) > MAX_DISCIPLINE_CHARS:
            raise BadRequest("discipline must be at most 40 characters")
        extra["discipline"] = discipline.strip()
    return question.strip(), language, area, mode, use_case, extra


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
        question, language, area, mode, use_case, extra = _parse(body)
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
                TwinQuestion(question=question, tier=tier, language=language, area=area, mode="question",
                             conversation_id=conversation_id, channel="voice", use_case=use_case, params=extra)
            )
    except Exception:  # the caller hears a fixed sentence, never a stack trace
        log.exception("orchestrator failed for conversation %s", conversation_id)
        return 200, error_speech(language)
    return 200, to_speech(answer, language)
