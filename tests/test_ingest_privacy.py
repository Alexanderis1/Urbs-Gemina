from pathlib import Path

from twin.ingest.catalog import load_catalog
from twin.ingest.privacy import is_personal_field, strip_personal_fields

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = load_catalog(ROOT / "config" / "ingest.yaml").privacy_patterns


def test_roma_241_contact_fields_are_personal() -> None:
    for name in ["ref-nome", "ref-cell", "telefono", "e-mail", "Telefono", "EMAIL", "pec", "fax"]:
        assert is_personal_field(name, PATTERNS), name


def test_osm_contact_tags_are_personal() -> None:
    for name in ["phone", "contact:phone", "contact:email", "contact:website", "operator:phone", "email"]:
        assert is_personal_field(name, PATTERNS), name


def test_ordinary_fields_are_kept() -> None:
    for name in ["nome", "denominazione", "castello", "municipio", "ref", "indirizzo", "posti_letto",
                 "specie", "hotel", "name", "addr:street"]:
        assert not is_personal_field(name, PATTERNS), name


def test_strip_drops_fields_and_reports_them() -> None:
    collection = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None,
             "properties": {"nome": "RSA Villa", "ref-nome": "Mario Rossi", "ref-cell": "333", "telefono": "06"}},
            {"type": "Feature", "geometry": None, "properties": {"nome": "Asl", "e-mail": "x@y.it", "extra": 1}},
        ],
    }
    cleaned, dropped = strip_personal_fields(collection, PATTERNS, extra_fields=["extra"])
    assert cleaned["features"][0]["properties"] == {"nome": "RSA Villa"}
    assert cleaned["features"][1]["properties"] == {"nome": "Asl"}
    assert dropped == ["e-mail", "extra", "ref-cell", "ref-nome", "telefono"]
    # The input is left untouched; only the returned copy is cleaned.
    assert "ref-nome" in collection["features"][0]["properties"]  # type: ignore[index]


def test_null_properties_are_handled() -> None:
    cleaned, dropped = strip_personal_fields(
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": None, "properties": None}]},
        PATTERNS,
    )
    assert cleaned["features"][0]["properties"] == {}
    assert dropped == []
