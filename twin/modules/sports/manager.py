"""Manager update flow: a facility manager confirms or corrects a field.

A confirmed value replaces web-derived ones and is never overwritten by later
web runs. Every change returns an audit record (who, when, before, after).
``account_ref`` is an organisational account id (e.g. "org:asd-bernardini"),
never a person's name. Storage and login live in the web app (Supabase).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from twin.modules.sports.config import SportsConfig
from twin.modules.sports.disciplines import discipline_id
from twin.modules.sports.model import FieldValue, Facility, Provenance

EDITABLE = ("disciplines", "hours", "accessibility", "contact", "name")


@dataclass(frozen=True)
class ManagerUpdate:
    facility_id: str
    field: str
    value: Any
    account_ref: str
    confirmed_at: str


def apply_manager_update(facility: Facility, update: ManagerUpdate,
                         config: SportsConfig) -> tuple[Facility, dict[str, Any]]:
    if update.facility_id != facility.facility_id:
        raise ValueError("update is for another facility")
    if update.field not in EDITABLE:
        raise ValueError(f"field {update.field!r} cannot be edited; allowed: {EDITABLE}")
    prov = (Provenance("manager", update.account_ref, retrieved_at=update.confirmed_at),)

    if update.field == "disciplines":
        values = [update.value] if isinstance(update.value, str) else list(update.value)
        ids = [discipline_id(str(v), config) for v in values]
        unknown = [v for v, i in zip(values, ids) if i is None]
        if unknown:
            raise ValueError(f"unknown disciplines: {unknown}")
        before: Any = sorted(facility.disciplines)
        disciplines = {i: FieldValue(True, "manager_confirmed", prov) for i in sorted({i for i in ids if i})}
        updated = facility.with_changes(disciplines=disciplines)
        after: Any = sorted(disciplines)
    else:
        before = facility.fields.get(update.field, FieldValue(None, "not_known")).value
        fields = dict(facility.fields)
        fields[update.field] = FieldValue(update.value, "manager_confirmed", prov)
        updated = facility.with_changes(fields=fields)
        after = update.value

    audit = {"facility_id": facility.facility_id, "field": update.field, "before": before, "after": after,
             "account_ref": update.account_ref, "confirmed_at": update.confirmed_at}
    return updated, audit
