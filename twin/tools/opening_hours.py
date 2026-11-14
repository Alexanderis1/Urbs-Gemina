"""Is a place open at a given moment? A small reader of OpenStreetMap ``opening_hours`` text.

Covers the forms used by most Rome venues: ``24/7``; weekday lists and ranges (``Mo-Fr``,
``Mo,We``, ``Fr-Mo``); month ranges (``Nov-Mar``); several time ranges (``08:00-13:00,14:00-20:00``),
ranges past midnight (``18:00-02:00``) and ``off``/``closed``. Rules are read left to right and a
later rule replaces earlier ones for the days it names, as the OSM specification says. ``||``
starts a fallback, which is ignored. Holiday rules (``PH``, ``SH``) are skipped. Anything else
(``sunrise``, ``week``, open ends ``+``, free text) gives ``None``: the hours are unknown, never guessed.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_TIME = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
_DAY_TOKEN = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(-(Mo|Tu|We|Th|Fr|Sa|Su))?$")
_MONTH_TOKEN = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))?$")

#: minutes from midnight, [start, end); end may exceed 1440 for ranges past midnight
Span = tuple[int, int]


class _Unknown(ValueError):
    pass


def _cyclic(names: list[str], first: str, last: str | None) -> set[int]:
    a = names.index(first)
    b = names.index(last) if last else a
    out = {a}
    while a != b:
        a = (a + 1) % len(names)
        out.add(a)
    return out


def _parse_selector(tokens: list[str], pattern: re.Pattern[str], names: list[str]) -> set[int] | None:
    found: set[int] = set()
    for token in tokens:
        match = pattern.match(token)
        if not match:
            return None
        found |= _cyclic(names, match.group(1), match.group(3))
    return found


def _parse_rule(rule: str) -> tuple[set[int] | None, set[int] | None, list[Span]] | None:
    """(months or None = all, weekdays or None = all, spans) or None for a holiday rule to skip."""
    words = rule.split()
    months: set[int] | None = None
    days: set[int] | None = None
    if words:
        parsed = _parse_selector(words[0].split(","), _MONTH_TOKEN, MONTHS)
        if parsed is not None:
            months, words = parsed, words[1:]
    if words:
        tokens = words[0].split(",")
        if any(t in ("PH", "SH") for t in tokens):
            plain = [t for t in tokens if t not in ("PH", "SH")]
            if not plain:
                return None
            tokens = plain
        parsed = _parse_selector(tokens, _DAY_TOKEN, DAYS)
        if parsed is not None:
            days, words = parsed, words[1:]
    rest = " ".join(words).strip()
    if rest in ("off", "closed"):
        return months, days, []
    if not rest:
        raise _Unknown(rule)
    spans: list[Span] = []
    for part in rest.split(","):
        match = _TIME.match(part.strip())
        if not match:
            raise _Unknown(rule)
        h1, m1, h2, m2 = (int(g) for g in match.groups())
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 1440
        spans.append((start, end))
    return months, days, spans


def _spans_for(rules: list[tuple[set[int] | None, set[int] | None, list[Span]]], day: datetime) -> list[Span]:
    spans: list[Span] = []
    for months, days, rule_spans in rules:
        if months is not None and day.month - 1 not in months:
            continue
        if days is not None and day.weekday() not in days:
            continue
        spans = rule_spans  # a later matching rule replaces the earlier one for this day
    return spans


def is_open(spec: str | None, at: datetime) -> bool | None:
    """True / False when the text can be read, None when the hours are unknown or not understood."""
    text = (spec or "").strip()
    if not text:
        return None
    if text == "24/7":
        return True
    text = text.split("||")[0].strip()
    local = (at if at.tzinfo else at.replace(tzinfo=ROME)).astimezone(ROME)
    try:
        rules = [r for r in (_parse_rule(part.strip()) for part in text.split(";") if part.strip()) if r is not None]
    except _Unknown:
        return None
    if not rules:
        return None
    minute = local.hour * 60 + local.minute
    if any(s <= minute < e for s, e in _spans_for(rules, local)):
        return True
    yesterday = local - timedelta(days=1)
    return any(s <= minute + 1440 < e for s, e in _spans_for(rules, yesterday))


_IT_DAYS = {"lun": "Mo", "mar": "Tu", "mer": "We", "gio": "Th", "giov": "Th", "ven": "Fr", "sab": "Sa", "dom": "Su"}
_IT_TIME = re.compile(r"^(\d{1,2})(?:[:.](\d{2}))?-(\d{1,2})(?:[:.](\d{2}))?$")
_IT_DATE = re.compile(r"\b\d{1,2}(-\d{1,2})?\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)\b", re.IGNORECASE)


def from_italian(text: str | None) -> str | None:
    """Rome open-data hours ('Lun-Ven 9-19, Sab 10-13') as OSM opening_hours text, or None when unclear.

    Parts with calendar dates ('24-31 dic ...') are dropped (exceptions); parentheses, seasons or
    anything else not understood give None, so the place shows "hours unknown" instead of a guess.
    """
    raw = (text or "").strip()
    if not raw or raw.lower() in ("n.d.", "nd", "-"):
        return None
    if any(ch in raw for ch in "();") or "estate" in raw.lower() or "inverno" in raw.lower():
        return None
    rules: list[str] = []
    for part in (p.strip() for p in raw.split(",")):
        if not part:
            continue
        if _IT_DATE.search(part):
            continue
        words = part.replace(" e ", ",").split()
        if len(words) != 2:
            return None
        day_part, time_part = words
        groups: list[str] = []
        for chunk in day_part.split(","):
            names = [n.strip().lower() for n in chunk.split("-")]
            if any(n not in _IT_DAYS for n in names):
                return None
            codes = [_IT_DAYS[n] for n in names]
            groups.append("-".join(codes) if len(codes) == 2 else ",".join(codes))
        match = _IT_TIME.match(time_part)
        if not match:
            return None
        h1, m1, h2, m2 = match.groups()
        rules.append(f"{','.join(groups)} {int(h1):02d}:{m1 or '00'}-{int(h2):02d}:{m2 or '00'}")
    return "; ".join(rules) or None
