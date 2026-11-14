"""Regione Lazio daily gauges: parsing the monthly CSV files and placing stations."""
from datetime import date

from twin.providers.open import lazio_gauges as lg

TERMO = "Stazioni;Data;T-MIN;T-MAX\nRoma Macao;01/08/2025;24,1;35,6\nRoma Macao;02/08/2025;;34,0\nAbbadia S.Salvatore;01/08/2025;14,2;28,3\n"
PLUVIO = "Stazione;Data;Dato pluviometrico giornaliero 0-24\nRoma Macao ;03/09/2024;61,4\nRoma Macao ;04/09/2024;-\n"


def test_temperature_rows_parse_with_decimal_commas() -> None:
    rows = list(lg.parse_temperature(TERMO))
    assert rows[0] == lg.DailyTemperature("Roma Macao", date(2025, 8, 1), 24.1, 35.6)
    assert rows[1].t_min is None and rows[1].t_max == 34.0


def test_rain_rows_skip_missing_values_and_trim_names() -> None:
    rows = list(lg.parse_rain(PLUVIO))
    assert rows == [lg.DailyRain("Roma Macao", date(2024, 9, 3), 61.4)]


def test_only_rome_stations_with_known_positions_are_kept() -> None:
    gauges = lg.load_gauges()
    kept = lg.in_rome(lg.parse_temperature(TERMO), gauges)
    assert {r.station for r in kept} == {"Roma Macao"}
    macao = gauges[lg.norm("Roma Macao")]
    assert macao.temperature and abs(macao.lat - 41.904) < 1e-3 and abs(macao.lon - 12.507) < 1e-3


def test_names_match_despite_spacing_and_case() -> None:
    assert lg.norm("Tevere a Castelgiubileo ") == lg.norm("TEVERE A CASTELGIUBILEO")
    assert lg.norm("Collegio Romano") in lg.load_gauges()
