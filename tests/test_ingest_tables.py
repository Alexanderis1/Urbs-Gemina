"""Official tables (CSV) turned into point layers: with coordinates, or geocoded offline."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

gpd = pytest.importorskip("geopandas")
osmium = pytest.importorskip("osmium")

from twin.ingest.catalog import load_catalog  # noqa: E402
from twin.ingest.http import HttpRequest  # noqa: E402
from twin.ingest.static import ingest_layer  # noqa: E402
from twin.ingest.tables import (  # noqa: E402
    AddressIndex,
    normalise_street,
    split_address,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT / "config" / "ingest.yaml")
NOW = datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)


# --- address helpers -----------------------------------------------------------

def test_street_names_are_normalised() -> None:
    assert normalise_street("Via Dei Portoghesi") == "via dei portoghesi"
    assert normalise_street("P.zza  Colonna") == "piazza colonna"
    assert normalise_street("V.le di Trastevere") == "viale di trastevere"
    assert normalise_street("Largo Antonio Ruberti") == "largo antonio ruberti"
    assert normalise_street("Via dell'Università") == "via dell universita"


def test_addresses_split_into_street_and_number() -> None:
    assert split_address("Via Dei Portoghesi, 12") == ("via dei portoghesi", "12")
    assert split_address("Piazzale Porta Pia 1") == ("piazzale porta pia", "1")
    assert split_address("Viale di Trastevere, 76/A") == ("viale di trastevere", "76a")
    assert split_address("Palazzo Viminale") == ("palazzo viminale", None)
    # Postcode, city or building name after the number are ignored.
    assert split_address("Via di Santa Maria Maggiore 164 00184") == ("via di santa maria maggiore", "164")
    assert split_address("Piazza Del Quirinale, 41 Palazzo Della Consulta") == ("piazza del quirinale", "41")
    assert split_address("Via Volturno, 58 Roma") == ("via volturno", "58")
    assert split_address("Viale XXI Aprile, 51") == ("viale xxi aprile", "51")


def test_index_finds_exact_then_street_then_initials() -> None:
    index = AddressIndex([
        ("Via dei Portoghesi", "12", 12.47, 41.90),
        ("Viale di Trastevere", "76", 12.47, 41.88),
        ("Via Cristoforo Colombo", "40", 12.48, 41.86),
        ("Via Cristoforo Colombo", "50", 12.49, 41.85),
    ])
    assert index.lookup("Via Dei Portoghesi, 12") == (12.47, 41.90, "address")
    assert index.lookup("Viale di Trastevere, 76/A") == (12.47, 41.88, "address")  # suffix dropped
    lon, lat, quality = index.lookup("Via C. Colombo, 44")  # type: ignore[misc]
    assert quality == "street"  # no number 44: centre of the street's addresses
    assert lon == pytest.approx(12.485) and lat == pytest.approx(41.855)
    assert index.lookup("Via Inesistente 3") is None


def test_initials_pick_the_right_street_and_roads_without_addresses_count() -> None:
    index = AddressIndex(
        [("Via Cristoforo Colombo", "40", 12.48, 41.86), ("Via Luigi Colombo", "2", 12.60, 41.95)],
        streets=[("Via del Collegio Romano", 12.481, 41.898)],
    )
    assert index.lookup("Via C. Colombo, 44")[:2] == (12.48, 41.86)  # type: ignore[index]
    assert index.lookup("Via del Collegio Romano 27") == (12.481, 41.898, "street")


# --- layers ----------------------------------------------------------------------

CLINICS_CSV = (
    "N,ID_PR,ASL,RAGIONE SOCIALE,PARTITA IVA,NOME PRESIDIO,DECRETI,TIPO DI PROVVEDIMENTO,INDIRIZZO,COMUNE,CAP,Latitude,Longitude\n"
    '1,11,RM/A,ALFA SRL,123,CASA DI CURA ALFA,D1,DECRETO,"VIA A, 1",ROMA,00100,41.90,12.50\n'
    '2,12,RM/A,ROSSI MARIO & C. S.A.S.,456,CENTRO FISIOTERAPICO DI ROSSI MARIO & C. S.A.S.,D2,DECRETO,"VIA B, 2",ROMA,00100,41.91,12.51\n'
    '3,13,RM/F,BETA SRL,789,BETA,D3,DECRETO,"VIA C, 3",CIVITAVECCHIA,00053,42.09,11.79\n'
    '4,14,RM/A,GAMMA SRL,000,GAMMA,D4,DECRETO,"VIA D, 4",ROMA,00100,,\n'
)


def test_accredited_clinics_keep_only_safe_columns(tmp_path: Path) -> None:
    def fetch(request: HttpRequest) -> bytes:
        return CLINICS_CSV.encode("utf-8")

    entry = ingest_layer(CATALOG.layers["health_accredited_lazio"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    assert entry["features"] == 2  # Civitavecchia is outside Rome, GAMMA has no coordinates
    assert entry["skipped_rows"] == {"filtered": 1, "no_position": 1}
    frame = gpd.read_parquet(tmp_path / "health_accredited_lazio.parquet")
    assert set(frame.columns) == {"facility_id", "name", "geometry"}
    names = sorted(frame["name"])
    # A partnership name carries a person's name: replaced by a generic label.
    assert names == ["CASA DI CURA ALFA", "Struttura sanitaria accreditata"]
    text = (tmp_path / "health_accredited_lazio.geojson").read_text(encoding="utf-8")
    for secret in ("ROSSI", "PARTITA", "456", "VIA B"):
        assert secret not in text


IPA_TXT = (
    "﻿cod_amm\tdes_amm\tComune\tnome_resp\tcogn_resp\tIndirizzo\ttipologia_istat\tmail1\n"
    "m_it\tMinistero dell'Interno\tRoma\tMario\tRossi\tPalazzo Viminale\t"
    "Presidenza del Consiglio dei Ministri, Ministeri e Avvocatura dello Stato\tx@y.it\n"
    "ads\tAvvocatura dello Stato\tRoma\tAnna\tBianchi\tVia Dei Portoghesi, 12\t"
    "Presidenza del Consiglio dei Ministri, Ministeri e Avvocatura dello Stato\ta@b.it\n"
    "scu\tLiceo X\tRoma\tLuca\tVerdi\tVia dei Portoghesi, 12\tIstituti di Istruzione Statale di Ogni Ordine e Grado\tc@d.it\n"
    "mil\tMinistero finto\tMilano\tA\tB\tVia Roma 1\t"
    "Presidenza del Consiglio dei Ministri, Ministeri e Avvocatura dello Stato\te@f.it\n"
    "lost\tAutorita' Z\tRoma\tA\tB\tVia Nowhere 9\tAutorita' Amministrative Indipendenti\tg@h.it\n"
)

OSM_ADDRESSES = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" version="1" lat="41.9010" lon="12.4740"><tag k="addr:street" v="Via dei Portoghesi"/><tag k="addr:housenumber" v="12"/></node>
  <node id="2" version="1" lat="41.9000" lon="12.4950"><tag k="addr:street" v="Piazza del Viminale"/><tag k="addr:housenumber" v="1"/></node>
  <node id="3" version="1" lat="45.0" lon="9.0"><tag k="addr:street" v="Via Roma"/><tag k="addr:housenumber" v="1"/></node>
</osm>
"""


def test_public_bodies_are_geocoded_offline_without_people(tmp_path: Path) -> None:
    def fetch(request: HttpRequest) -> bytes:
        if request.url.endswith(".osm.pbf"):
            return OSM_ADDRESSES.encode()
        return IPA_TXT.encode("utf-8")

    entry = ingest_layer(CATALOG.layers["public_bodies_ipa"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    assert entry["features"] == 2
    assert entry["geocoding"] == {"address": 2, "street": 0, "not_found": 1}
    assert entry["skipped_rows"]["filtered"] == 2  # the school and the Milan row
    frame = gpd.read_parquet(tmp_path / "public_bodies_ipa.parquet")
    assert set(frame.columns) == {"ipa_code", "name", "body_type", "geocode_quality", "data_kind", "geometry"}
    viminale = frame[frame["ipa_code"] == "m_it"].iloc[0]
    assert viminale.geometry.x == pytest.approx(12.495)  # address override: Piazza del Viminale 1
    assert set(frame["data_kind"]) == {"real"}
    text = json.dumps(json.loads((tmp_path / "public_bodies_ipa.geojson").read_text(encoding="utf-8")))
    for secret in ("Rossi", "Bianchi", "x@y.it", "Mario"):
        assert secret not in text
