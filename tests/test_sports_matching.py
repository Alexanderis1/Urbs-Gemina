from __future__ import annotations

from tests.sports_fixtures import at, geoserver_sports, osm_elements
from twin.modules.sports.config import load_config
from twin.modules.sports.disciplines import disciplines_from_osm, disciplines_from_text
from twin.modules.sports.matching import build_facilities, name_similarity, normalize_name
from twin.modules.sports.model import Candidate
from twin.modules.sports.sources import from_geoserver_sports, from_osm, from_rows

CFG = load_config()


def test_normalize_name_drops_accents_punctuation_and_stopwords() -> None:
    assert normalize_name("A.S.D. Centro Sportivo Città di Roma", CFG.matching.name_stopwords) == ("citta",)


def test_name_similarity_ignores_generic_words() -> None:
    stop = CFG.matching.name_stopwords
    assert name_similarity("Centro Sportivo Fulvio Bernardini", "Fulvio Bernardini", stop) == 1.0
    assert name_similarity("Piscina Quadraro", "Campo Bocce Cinecitta", stop) < 0.5
    assert name_similarity("", "Anything", stop) == 0.0
    # Seen on real data: the web writes "Torre Spaccata", the registry "Torrespaccata".
    assert name_similarity("Piscine di Torre Spaccata", "Piscine Di Torrespaccata", stop) >= 0.92


def test_disciplines_from_text_and_osm() -> None:
    assert disciplines_from_text("Piscina comunale e pallavolo", CFG) == {"swimming", "volleyball"}
    assert disciplines_from_osm({"sport": "soccer;tennis"}, CFG) == {"football", "tennis"}
    assert disciplines_from_osm({"leisure": "swimming_pool"}, CFG) == {"swimming"}


def test_geoserver_adapter_drops_personal_fields_and_private_holder() -> None:
    cands = from_geoserver_sports(geoserver_sports(), CFG, retrieved_at="2026-11-13")
    assert [c.name for c in cands][:2] == ["Centro Sportivo Fulvio Bernardini", "Piscina Comunale Quadraro"]
    first, pool = cands[0], cands[1]
    assert "REF_TEL" not in first.attributes and "3331234567" not in str(first.attributes)
    assert first.attributes["manager"] == "A.S.D. Bernardini"
    assert "manager" not in pool.attributes  # "Mario Rossi" may be a private person
    assert first.municipio == "VII"
    assert first.disciplines == frozenset({"football"})
    assert pool.disciplines == frozenset({"swimming"})


def test_osm_adapter_keeps_sport_places_only_and_no_phone() -> None:
    cands = from_osm(osm_elements(), CFG, retrieved_at="2026-11-13")
    assert [c.record_id for c in cands] == ["way/11", "node/12", "node/13", "node/15"]
    assert "phone" not in cands[0].attributes
    assert cands[0].attributes["website"] == "https://bernardini.example"


def test_build_facilities_merges_duplicates_but_not_same_source_neighbours() -> None:
    cands = from_geoserver_sports(geoserver_sports(), CFG, "2026-11-13") + from_osm(osm_elements(), CFG, "2026-11-13")
    facilities, report = build_facilities(cands, CFG)
    by_name = {f.fields["name"].value: f for f in facilities}
    assert len(facilities) == 5
    bern = by_name["Centro Sportivo Fulvio Bernardini"]
    assert set(bern.members) == {"roma_sports_municipal:243.1", "osm:way/11"}
    # Official record wins the position; disciplines are the union with provenance.
    assert (bern.lon, bern.lat) == at(0, 0)
    assert set(bern.disciplines) == {"football", "tennis"}
    assert bern.disciplines["tennis"].status == "open_data"
    assert bern.disciplines["football"].status == "official"
    # The bocce field is 15 m away but from the same official source: never merged.
    assert "Campo Bocce Cinecitta" in by_name
    assert len(report.links) == 2
    # Accessibility is never invented.
    assert bern.fields["accessibility"].status == "not_known"


def test_ids_are_stable_whatever_the_input_order() -> None:
    cands = from_geoserver_sports(geoserver_sports(), CFG, "x") + from_osm(osm_elements(), CFG, "x")
    ids_a = sorted(f.facility_id for f in build_facilities(cands, CFG)[0])
    ids_b = sorted(f.facility_id for f in build_facilities(list(reversed(cands)), CFG)[0])
    assert ids_a == ids_b


def test_unlocated_record_matches_on_near_exact_name_in_same_municipio() -> None:
    rows = [
        {"NOME": "Piscina Comunale Quadraro", "MUNICIPIO": "7"},
        {"NOME": "Palestra Scuola Pinco", "MUNICIPIO": "VII"},
    ]
    cands = from_geoserver_sports(geoserver_sports(), CFG, "x") + from_rows(
        "roma_d30_centres", rows, CFG, retrieved_at="x", default_kind="school_gym")
    facilities, report = build_facilities(cands, CFG)
    pool = next(f for f in facilities if "roma_sports_municipal:243.2" in f.members)
    assert "roma_d30_centres:row/0" in pool.members
    lonely = next(f for f in facilities if "roma_d30_centres:row/1" in f.members)
    assert lonely.lon is None
    assert report.unlocated == ["roma_d30_centres:row/1"]


def test_web_candidate_disciplines_are_labelled_unverified() -> None:
    lon, lat = at(5, 5)
    web = Candidate(source="web", record_id="w1", name="Fulvio Bernardini", lon=lon, lat=lat, kind="sports_centre",
                    municipio="VII", address=None, disciplines=frozenset({"padel"}), attributes={},
                    url="https://municipio7.example/sport", retrieved_at="2026-11-13", confidence=0.7)
    facilities, _ = build_facilities(from_geoserver_sports(geoserver_sports(), CFG, "x") + [web], CFG)
    bern = next(f for f in facilities if "web:w1" in f.members)
    padel = bern.disciplines["padel"]
    assert padel.status == "web_unverified"
    assert padel.label == "from the web, unverified"
    assert padel.provenance[0].url == "https://municipio7.example/sport"


def test_real_geoserver_field_names() -> None:
    """Property names as served by DIPPC:243 and GABSIN:piscine on 2026-11-13."""
    from twin.modules.sports.sources import from_geoserver_pools

    sports = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": "243_ServiziSportivi.1",
        "geometry": {"type": "Point", "coordinates": [12.473733, 41.91746804]},
        "properties": {"id_pec": 9, "mun": "2", "tipologia": "Sport equestri, maneggi", "indirizzo": "Via Flaminia, 158",
                       "nome": "Circolo Belle Arti", "concessio": "A.S.D. CIRCOLO BELLE ARTI", "attivo": "SI",
                       "scadenza_": "31/12/2021", "tel1": "06 3226529", "email1": "info@example.it"}}]}
    c = from_geoserver_sports(sports, CFG, "x")[0]
    assert (c.record_id, c.municipio, c.address) == ("243_ServiziSportivi.1", "II", "Via Flaminia, 158")
    assert c.attributes == {"active": "SI", "concession_expiry": "31/12/2021", "manager": "A.S.D. CIRCOLO BELLE ARTI"}
    assert c.disciplines == frozenset({"equestrian"})
    pools = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "id": "piscine.1", "geometry": {"type": "Point", "coordinates": [12.49, 41.93]},
        "properties": {"nome": "Circolo Montecitorio", "municipio": "II", "giorni_ap7": "22 giu - 31 ago",
                       "orario_70": "10-19", "sito_web": "<a href=https://www.circolomontecitorio.it target=_blank >sito</a>"}}]}
    p = from_geoserver_pools(pools, CFG, "x")[0]
    assert p.attributes == {"hours": "10-19", "opening_period": "22 giu - 31 ago",
                            "website": "https://www.circolomontecitorio.it"}
    assert p.disciplines == frozenset({"swimming"})
