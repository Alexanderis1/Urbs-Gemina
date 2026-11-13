from __future__ import annotations

from tests.sports_fixtures import geoserver_sports
from twin.modules.sports.config import load_config
from twin.modules.sports.manager import ManagerUpdate, apply_manager_update
from twin.modules.sports.matching import build_facilities
from twin.modules.sports.sources import from_geoserver_sports
from twin.modules.sports.web_fields import apply_enrichment, scout_candidates, validate_enrichment

CFG = load_config()
SRC = "https://www.comune.roma.it/web/it/municipio-vii-sport.page"


def bernardini():  # type: ignore[no-untyped-def]
    facilities, _ = build_facilities(from_geoserver_sports(geoserver_sports(), CFG, "2026-11-13"), CFG)
    return next(f for f in facilities if f.fields["name"].value.endswith("Bernardini"))


RAW = {
    "facility_id": "ignored-here",
    "disciplines": [
        {"value": "Tennis", "source_url": SRC, "confidence": 0.8, "quote": "corsi di tennis"},
        {"value": "padel", "source_url": SRC, "confidence": 0.3, "quote": "padel?"},
        {"value": "quidditch", "source_url": SRC, "confidence": 0.9, "quote": "..."},
        {"value": "basket", "source_url": "javascript:alert(1)", "confidence": 0.9, "quote": "basket"},
    ],
    "hours": {"value": "Mon-Fri 9-22", "source_url": SRC, "confidence": 0.7, "quote": "aperto 9-22"},
    "accessibility": {"value": "accessible", "source_url": SRC, "confidence": 0.9, "quote": "struttura moderna"},
    "contact": {"emails": ["info@bernardini.it", "mario.rossi@gmail.com"], "phones": ["06 1234567", "333 1234567"],
                "website": "https://bernardini.it", "source_url": SRC, "confidence": 0.9},
}


def test_validate_enrichment_applies_every_rule() -> None:
    fields, warnings = validate_enrichment(RAW, CFG, retrieved_at="2026-11-13")
    assert set(fields.disciplines) == {"tennis"}  # low confidence, unknown and non-http dropped
    assert fields.disciplines["tennis"].status == "web_unverified"
    assert fields.disciplines["tennis"].provenance[0].quote == "corsi di tennis"
    assert fields.hours is not None and fields.hours.label == "from the web, unverified"
    # The quote never mentions accessibility, so it stays "not known".
    assert fields.accessibility is None
    assert fields.contact is not None
    assert fields.contact.value == {"emails": ["info@bernardini.it"], "phones": ["06 1234567"],
                                    "website": "https://bernardini.it"}
    assert len(warnings) >= 4


def test_accessibility_kept_only_when_source_states_it() -> None:
    raw = {"accessibility": {"value": "accessible", "source_url": SRC, "confidence": 0.8,
                             "quote": "Impianto privo di barriere architettoniche"}}
    fields, _ = validate_enrichment(raw, CFG, retrieved_at="2026-11-13")
    assert fields.accessibility is not None and fields.accessibility.value == "accessible"


def test_apply_enrichment_never_overrides_official_or_confirmed() -> None:
    fac = bernardini()
    fields, _ = validate_enrichment(RAW, CFG, retrieved_at="2026-11-13")
    enriched = apply_enrichment(fac, fields)
    assert enriched.disciplines["football"].status == "official"
    assert enriched.disciplines["tennis"].status == "web_unverified"
    assert enriched.fields["hours"].status == "web_unverified"
    assert enriched.fields["accessibility"].status == "not_known"


def test_manager_confirmation_replaces_web_values_and_is_audited() -> None:
    fac = bernardini()
    fields, _ = validate_enrichment(RAW, CFG, retrieved_at="2026-11-13")
    enriched = apply_enrichment(fac, fields)
    update = ManagerUpdate(facility_id=enriched.facility_id, field="disciplines", value=["football", "padel"],
                           account_ref="org:asd-bernardini", confirmed_at="2026-11-14T09:00:00Z")
    updated, audit = apply_manager_update(enriched, update, CFG)
    assert set(updated.disciplines) == {"football", "padel"}
    assert all(v.status == "manager_confirmed" for v in updated.disciplines.values())
    assert audit["before"] == sorted(enriched.disciplines)
    assert audit["after"] == ["football", "padel"]
    hours = ManagerUpdate(enriched.facility_id, "hours", "Mon-Sat 8-23", "org:asd-bernardini", "2026-11-14T09:01:00Z")
    updated2, _ = apply_manager_update(updated, hours, CFG)
    assert updated2.fields["hours"].status == "manager_confirmed"
    # Later web runs cannot overwrite what the manager confirmed.
    again = apply_enrichment(updated2, fields)
    assert again.fields["hours"].value == "Mon-Sat 8-23"
    assert "tennis" not in again.disciplines


def test_manager_update_rejects_wrong_facility_and_unknown_field() -> None:
    import pytest

    fac = bernardini()
    with pytest.raises(ValueError):
        apply_manager_update(fac, ManagerUpdate("other", "hours", "x", "org:a", "t"), CFG)
    with pytest.raises(ValueError):
        apply_manager_update(fac, ManagerUpdate(fac.facility_id, "owner_phone", "x", "org:a", "t"), CFG)
    with pytest.raises(ValueError):
        apply_manager_update(fac, ManagerUpdate(fac.facility_id, "disciplines", ["quidditch"], "org:a", "t"), CFG)


def test_scout_candidates_become_unlocated_web_candidates() -> None:
    raw = [
        {"name": "Palestra IC Via Anagni", "address": "Via Anagni 10", "municipio": "VII", "kind": "school_gym",
         "disciplines": ["pallavolo"], "source_url": SRC, "confidence": 0.7},
        {"name": "No source", "municipio": "VII", "confidence": 0.9},
        {"name": "Weak", "source_url": SRC, "confidence": 0.2},
    ]
    cands, warnings = scout_candidates(raw, CFG, retrieved_at="2026-11-13")
    assert len(cands) == 1
    c = cands[0]
    assert c.source == "web" and c.lon is None and c.disciplines == frozenset({"volleyball"})
    assert c.url == SRC
    assert len(warnings) == 2
