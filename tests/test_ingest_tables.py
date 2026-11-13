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


# --- health system (Ministry of Health open data) --------------------------------

from twin.ingest.tables import aggregate_rows  # noqa: E402


def test_bed_rows_are_summed_per_hospital_with_one_column_per_type() -> None:
    rows = [
        {"code": "1", "name": "A", "type": "ACUTI", "beds": "1.200"},
        {"code": "1", "name": "A", "type": "RIABILITAZIONE", "beds": "30"},
        {"code": "2", "name": "B", "type": "ACUTI", "beds": "10"},
    ]
    spec = {"by": ["code"], "first": ["name"], "pivot": {"column": "type", "value": "beds", "prefix": "beds_"},
            "total": "beds_total"}
    out = sorted(aggregate_rows(rows, spec), key=lambda r: r["code"])
    assert out[0] == {"code": "1", "name": "A", "beds_acuti": "1200", "beds_riabilitazione": "30", "beds_total": "1230"}
    assert out[1]["beds_total"] == "10" and out[1].get("beds_riabilitazione", "0") == "0"


ASL_MAP = (
    "ANNO;CODICE REGIONE;DENOMINAZIONE REGIONE;CODICE AZIENDA;DENOMINAZIONE AZIENDA;CODICE COMUNE;COMUNE;MASCHI;FEMMINE;TOTALE\n"
    "2024;120;LAZIO ;201;ROMA 1;058091;ROMA (Municipi 1, 2);10;10;1.000\n"
    "2024;120;LAZIO ;202;ROMA 2;058091;ROMA (Municipi 3);5;5;500\n"
    "2024;120;LAZIO ;203;ROMA 3;058120;FIUMICINO ;1;1;80\n"
)
ASL_FACTS = (
    "Anno di Riferimento;Codice Regione;Codice Azienda Sanitaria Locale;Regione ;Denominazione ASL;Totale Residenti;"
    "Totale medici;Totale pediatri;Ambulatori e Laboratori;Numero medio punti di guardia medica;"
    "Assistenza Domiciliare Integrata Casi Trattati\n"
    "2022;120;201;LAZIO;ROMA 1;990;10;2;5;1;1.500\n"
    "2022;120;202;LAZIO;ROMA 2;480;4;1;3;1;700\n"
)


def test_asl_areas_are_built_from_municipi_with_official_figures(tmp_path: Path) -> None:
    from shapely.geometry import Point, box

    gpd.GeoDataFrame({"municipio": [1, 2, 3]},
                     geometry=[box(12.40, 41.80, 12.45, 41.85), box(12.45, 41.80, 12.50, 41.85),
                               box(12.50, 41.80, 12.55, 41.85)], crs="EPSG:4326").to_parquet(tmp_path / "municipi.parquet")
    gpd.GeoDataFrame({"beds_total": [100, 50]}, geometry=[Point(12.42, 41.82), Point(12.52, 41.82)],
                     crs="EPSG:4326").to_parquet(tmp_path / "hospital_beds_2023.parquet")
    gpd.GeoDataFrame({"name": ["c1", "c2"]}, geometry=[Point(12.47, 41.82), Point(12.52, 41.83)],
                     crs="EPSG:4326").to_parquet(tmp_path / "consultori_roma.parquet")

    def fetch(request: HttpRequest) -> bytes:
        return (ASL_MAP if "comuni" in request.url.lower() else ASL_FACTS).encode("latin-1")

    entry = ingest_layer(CATALOG.layers["asl_roma"], CATALOG, fetch, tmp_path, NOW)
    assert entry["status"] == "ok", entry.get("error")
    frame = gpd.read_parquet(tmp_path / "asl_roma.parquet").set_index("asl_name")
    assert list(frame.index) == ["ROMA 1", "ROMA 2"]  # Fiumicino is outside Roma Capitale
    one = frame.loc["ROMA 1"]
    assert one["municipi"] == "1, 2" and one["residents_2024"] == 1000
    assert one["gps_2022"] == 10 and one["home_care_cases_2022"] == 1500
    assert one["hospital_beds"] == 100 and one["consultori"] == 1
    assert one["beds_per_1000"] == pytest.approx(100.0)
    assert one["residents_per_gp"] == pytest.approx(99.0)  # official 2022 residents / GPs
    assert frame.loc["ROMA 2", "consultori"] == 1
