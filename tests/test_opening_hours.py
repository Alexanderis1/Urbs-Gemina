from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from twin.tools.opening_hours import is_open

ROME = ZoneInfo("Europe/Rome")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ROME)


# 2026-11-14 is a Saturday, 2026-11-16 a Monday.
@pytest.mark.parametrize("spec, moment, expected", [
    ("24/7", "2026-11-14T03:00", True),
    ("Mo-Fr 09:00-19:00", "2026-11-16T10:00", True),
    ("Mo-Fr 09:00-19:00", "2026-11-16T19:00", False),
    ("Mo-Fr 09:00-19:00", "2026-11-14T10:00", False),
    ("Mo-Fr 09:00-19:00; Sa 09:00-13:00", "2026-11-14T12:59", True),
    ("Mo-Fr 08:00-13:00,14:00-20:00", "2026-11-16T13:30", False),
    ("Mo-Fr 08:00-13:00,14:00-20:00", "2026-11-16T14:30", True),
    ("Mo,We,Fr 10:00-12:00", "2026-11-18T11:00", True),
    ("Mo,We,Fr 10:00-12:00", "2026-11-17T11:00", False),
    ("Tu-Su 09:00-19:00", "2026-11-16T10:00", False),
    ("Tu-Su 09:00-19:00", "2026-11-15T10:00", True),
    ("Fr-Mo 10:00-18:00", "2026-11-15T10:00", True),          # range across the week end
    ("Fr-Mo 10:00-18:00", "2026-11-18T10:00", False),
    ("09:00-18:00", "2026-11-15T17:00", True),                  # no day selector = every day
    ("Mo-Su 18:00-02:00", "2026-11-15T01:00", True),           # past midnight, from Saturday
    ("Mo-Su 09:00-19:00; Su off", "2026-11-15T10:00", False),  # a later rule replaces the day
    ("Mo-Sa 09:00-19:00; PH off", "2026-11-14T10:00", True),   # holiday rules are skipped
    ("Nov-Mar Mo-Su 09:00-17:00; Apr-Oct Mo-Su 09:00-19:00", "2026-11-14T18:00", False),
    ("Apr-Oct Mo-Su 09:00-19:00; Nov-Mar Mo-Su 09:00-17:00", "2026-11-14T16:00", True),
    ("Mo-Fr 09:00-19:00", "2026-11-14T10:00", False),
    ("Sa 10:00-12:00 || \"su appuntamento\"", "2026-11-14T11:00", True),
])
def test_known_rules(spec: str, moment: str, expected: bool) -> None:
    assert is_open(spec, at(moment)) is expected


@pytest.mark.parametrize("spec", ["", "su appuntamento", "sunrise-sunset", "Mo-Fr 09:00+", "week 1-53 Mo 10:00-12:00"])
def test_unknown_is_none(spec: str) -> None:
    assert is_open(spec, at("2026-11-16T10:00")) is None


def test_utc_moment_is_read_in_rome_time() -> None:
    # 08:30 UTC = 09:30 in Rome (winter time)
    assert is_open("Mo-Fr 09:00-10:00", datetime.fromisoformat("2026-11-16T08:30:00+00:00")) is True


@pytest.mark.parametrize("text, expected", [
    ("Lun-Ven 9-19", "Mo-Fr 09:00-19:00"),
    ("Mar-Dom 10:00-18:00", "Tu-Su 10:00-18:00"),
    ("Mar-Mer-Gio 9-18", "Tu,We,Th 09:00-18:00"),
    ("Mar e Gio 9-13", "Tu,Th 09:00-13:00"),
    ("Lun-Ven 10-18, Sab-Dom 10-14", "Mo-Fr 10:00-18:00; Sa-Su 10:00-14:00"),
    ("Lun-Giov 10-18", "Mo-Th 10:00-18:00"),
    ("Lun-Dom 9:30-19:30", "Mo-Su 09:30-19:30"),
    ("Mar-Dom 9:00-19:00, 24-31 dic 9:00-14:00", "Tu-Su 09:00-19:00"),   # date exceptions dropped
    ("n.d.", None),
    ("Lun-Dom 11-18 (Dom/festivi 10-18); estate: Lun-Dom 11-20", None),
])
def test_italian_hours(text: str, expected: str | None) -> None:
    from twin.tools.opening_hours import from_italian
    assert from_italian(text) == expected
