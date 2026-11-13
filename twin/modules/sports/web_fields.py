"""Check what the web agents return before it touches a facility.

The agents (agents/sports_scout, agents/sports_enrich) only propose. This code
decides, with fixed rules from config/sports.yaml ``web``:
  - every value needs an http(s) source URL and a confidence >= min_confidence;
  - disciplines must be in the vocabulary;
  - accessibility stays "not known" unless the quoted source text mentions it;
  - only organisational contacts survive (no personal e-mails, no mobiles);
  - everything kept is labelled "from the web, unverified";
  - web values never replace official or manager-confirmed ones.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.disciplines import discipline_id, fold
from twin.modules.sports.model import STATUS_RANK, Candidate, Facility, FieldValue, Provenance
from twin.modules.sports.sources import municipio_id

WEB = "web"


@dataclass
class EnrichmentFields:
    disciplines: dict[str, FieldValue] = field(default_factory=dict)
    hours: FieldValue | None = None
    accessibility: FieldValue | None = None
    contact: FieldValue | None = None


def _valid_url(url: Any) -> bool:
    return isinstance(url, str) and re.match(r"^https?://[^\s/$.?#][^\s]*$", url) is not None


def _confidence(raw: Mapping[str, Any]) -> float | None:
    try:
        value = float(raw.get("confidence"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def _accept(raw: Mapping[str, Any], what: str, config: SportsConfig, warnings: list[str]) -> float | None:
    if not _valid_url(raw.get("source_url")):
        warnings.append(f"{what}: dropped, no valid http(s) source URL")
        return None
    conf = _confidence(raw)
    if conf is None or conf < config.web.min_confidence:
        warnings.append(f"{what}: dropped, confidence {raw.get('confidence')!r} below {config.web.min_confidence}")
        return None
    return conf


def _web_value(value: Any, raw: Mapping[str, Any], conf: float, retrieved_at: str, record_id: str,
               config: SportsConfig) -> FieldValue:
    quote = raw.get("quote")
    prov = Provenance(WEB, record_id, str(raw["source_url"]), retrieved_at, conf,
                      str(quote)[:500] if quote else None)
    return FieldValue(value=value, status="web_unverified", provenance=(prov,), label=config.web.label_unverified)


def _org_email(email: str, config: SportsConfig) -> bool:
    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", email, re.IGNORECASE):
        return False
    local = email.split("@", 1)[0].lower()
    parts = re.split(r"[._\-+]", local)
    return local in config.web.org_email_local_parts or parts[0] in config.web.org_email_local_parts


def _org_phone(phone: str, config: SportsConfig) -> bool:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0039"):
        digits = digits[4:]
    elif digits.startswith("39") and len(digits) > 10:
        digits = digits[2:]
    if len(digits) < 6:
        return False
    return not (config.web.drop_mobile_numbers and digits.startswith("3"))


def validate_enrichment(raw: Mapping[str, Any], config: SportsConfig, retrieved_at: str,
                        record_id: str = "enrich") -> tuple[EnrichmentFields, list[str]]:
    out = EnrichmentFields()
    warnings: list[str] = []

    for item in raw.get("disciplines") or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("value", ""))
        conf = _accept(item, f"discipline {name!r}", config, warnings)
        if conf is None:
            continue
        did = discipline_id(name, config)
        if did is None:
            warnings.append(f"discipline {name!r}: dropped, not in the vocabulary")
            continue
        if did not in out.disciplines:
            out.disciplines[did] = _web_value(True, item, conf, retrieved_at, record_id, config)

    hours = raw.get("hours")
    if isinstance(hours, Mapping) and hours.get("value"):
        conf = _accept(hours, "hours", config, warnings)
        if conf is not None:
            out.hours = _web_value(str(hours["value"]), hours, conf, retrieved_at, record_id, config)

    acc = raw.get("accessibility")
    if isinstance(acc, Mapping) and acc.get("value"):
        conf = _accept(acc, "accessibility", config, warnings)
        quote = fold(str(acc.get("quote") or ""))
        if conf is not None:
            if any(fold(k) in quote for k in config.web.accessibility_keywords):
                out.accessibility = _web_value(str(acc["value"]), acc, conf, retrieved_at, record_id, config)
            else:
                warnings.append("accessibility: kept as 'not known', the quoted source does not state it")

    contact = raw.get("contact")
    if isinstance(contact, Mapping):
        conf = _accept(contact, "contact", config, warnings)
        if conf is not None:
            emails = [str(e) for e in contact.get("emails") or []]
            phones = [str(p) for p in contact.get("phones") or []]
            kept: dict[str, Any] = {
                "emails": [e for e in emails if _org_email(e, config)],
                "phones": [p for p in phones if _org_phone(p, config)],
            }
            dropped = len(emails) + len(phones) - len(kept["emails"]) - len(kept["phones"])
            if dropped:
                warnings.append(f"contact: dropped {dropped} value(s) that may be personal")
            if _valid_url(contact.get("website")):
                kept["website"] = contact["website"]
            if kept["emails"] or kept["phones"] or "website" in kept:
                out.contact = _web_value(kept, contact, conf, retrieved_at, record_id, config)
    return out, warnings


def _stronger(current: FieldValue | None, new: FieldValue) -> bool:
    return current is None or STATUS_RANK[new.status] > STATUS_RANK[current.status]


def apply_enrichment(facility: Facility, fields: EnrichmentFields) -> Facility:
    """Add web values where the facility has nothing better. Never downgrades a field.

    When the manager has confirmed the discipline list, web disciplines are ignored.
    """
    disciplines = dict(facility.disciplines)
    manager_set = any(v.status == "manager_confirmed" for v in disciplines.values())
    if not manager_set:
        for did, value in fields.disciplines.items():
            current = disciplines.get(did)
            if current is None:
                disciplines[did] = value
            elif current.status == "web_unverified":
                disciplines[did] = FieldValue(current.value, current.status,
                                              current.provenance + value.provenance, current.label)
    new_fields = dict(facility.fields)
    candidates: dict[str, FieldValue | None] = {
        "hours": fields.hours, "accessibility": fields.accessibility, "contact": fields.contact}
    for name, maybe in candidates.items():
        if maybe is not None and _stronger(new_fields.get(name), maybe):
            new_fields[name] = maybe
    return facility.with_changes(disciplines=disciplines, fields=new_fields)


def scout_candidates(raw: Sequence[Mapping[str, Any]], config: SportsConfig,
                     retrieved_at: str) -> tuple[list[Candidate], list[str]]:
    """Facility candidates found by a municipio scout. Located later by the geocoder, or matched by name."""
    out: list[Candidate] = []
    warnings: list[str] = []
    for i, item in enumerate(raw):
        name = str(item.get("name") or "").strip()
        conf = _accept(item, f"candidate {name!r}", config, warnings)
        if conf is None or not name:
            continue
        disciplines = {d for d in (discipline_id(str(x), config) for x in item.get("disciplines") or []) if d}
        lon, lat = item.get("lon"), item.get("lat")
        located = isinstance(lon, (int, float)) and isinstance(lat, (int, float))
        out.append(Candidate(
            source=WEB, record_id=f"scout/{i}", name=name,
            lon=float(lon) if located else None, lat=float(lat) if located else None,  # type: ignore[arg-type]
            kind=str(item.get("kind") or "sports_centre"), municipio=municipio_id(item.get("municipio")),
            address=str(item["address"]) if item.get("address") else None,
            disciplines=frozenset(disciplines),
            attributes={"appears_closed": True} if item.get("appears_closed") is True else {},
            url=str(item["source_url"]),
            retrieved_at=retrieved_at, confidence=conf,
        ))
    return out, warnings
