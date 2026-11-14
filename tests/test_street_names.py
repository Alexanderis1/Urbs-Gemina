from pathlib import Path

from twin.tools.street_names import StreetIndex, normalise, streets_in_text


def test_normalise_folds_accents_case_and_spaces() -> None:
    assert normalise("Viale  XVII Olimpiade") == "viale xvii olimpiade"
    assert normalise("Via Nicolò  V") == "via nicolo v"


def test_streets_in_text_finds_named_places() -> None:
    text = "Chiusura di viale del Sommergibile, nel tratto compreso tra via Domenico Baffigo e via Guido Vincon"
    assert streets_in_text(text)[:3] == ["viale del sommergibile", "via domenico baffigo", "via guido vincon"]
    assert streets_in_text("PIAZZA VENEZIA: CANTIERI STAZIONE METRO C")[0] == "piazza venezia"
    assert streets_in_text("Chiusa via Cavour") == ["via cavour"]


def test_index_locates_the_first_known_street(tmp_path: Path) -> None:
    path = tmp_path / "streets.csv"
    path.write_text("key,name,lon,lat,length_m\nvia cavour,Via Cavour,12.4932,41.8957,1500\n"
                    "piazza venezia,Piazza Venezia,12.4823,41.8960,300\n", encoding="utf-8")
    index = StreetIndex.load(path)
    found = index.locate("Per la chiusura di via Cavour, la linea devia da piazza Venezia")
    assert found is not None and found["name"] == "Via Cavour" and found["lon"] == 12.4932
    assert index.locate("Modifica temporanea percorso linea 89") is None


def test_short_name_matches_a_unique_full_name(tmp_path: Path) -> None:
    path = tmp_path / "streets.csv"
    path.write_text("key,name,lon,lat,length_m\nvia ferdinando gregorovius,Via Ferdinando Gregorovius,12.5,41.9,800\n"
                    "via siria,Via Siria,12.51,41.88,300\n", encoding="utf-8")
    found = StreetIndex.load(path).locate("Chiusura via Gregorovius. Deviazione da via Siria")
    assert found is not None and found["name"] == "Via Ferdinando Gregorovius"
