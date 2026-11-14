"""WS3: scheduled bus positions from the static GTFS timetable (fallback when the live feed is down)."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pytest

from twin.providers.base import ROME_BBOX
from twin.providers.open.gtfs_schedule import RomaGtfsScheduleProvider, ScheduleIndex
from twin.providers.settings import Settings


def _zip() -> bytes:
    files = {
        "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\n64,OP1,64,,3\nA,OP1,MEA,,1\n",
        "trips.txt": "route_id,service_id,trip_id\n64,WK,t1\n64,SUN,t2\nA,WK,t3\n",
        "calendar_dates.txt": "service_id,date,exception_type\nWK,20261113,1\nSUN,20261115,1\nWK,20261112,1\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\ns1,Termini,41.9000,12.5000\ns2,Venezia,41.8960,12.4830\n"
                     "s3,Vaticano,41.9020,12.4570\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "t1,08:00:00,08:00:00,s1,1\nt1,08:10:00,08:10:00,s2,2\nt1,08:20:00,08:20:00,s3,3\n"
                          "t2,08:00:00,08:00:00,s1,1\nt2,08:10:00,08:10:00,s2,2\n"
                          "t3,24:30:00,24:30:00,s1,1\nt3,24:40:00,24:40:00,s3,2\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_positions_are_interpolated_between_scheduled_stops() -> None:
    index = ScheduleIndex.build(_zip())
    # 13 Nov 2026 08:05 Rome time (UTC+1) = 07:05 UTC: trip t1 is halfway from Termini to Venezia.
    found = index.positions_at(datetime(2026, 11, 13, 7, 5, tzinfo=timezone.utc))
    assert [p.route for p in found] == ["64"]
    assert found[0].lon == pytest.approx(12.4915) and found[0].lat == pytest.approx(41.898)


def test_trips_after_midnight_belong_to_the_previous_service_day() -> None:
    index = ScheduleIndex.build(_zip())
    # 14 Nov 00:35 Rome = 13 Nov 23:35 UTC: t3 (service of 13 Nov, 24:30-24:40) is running.
    found = index.positions_at(datetime(2026, 11, 13, 23, 35, tzinfo=timezone.utc))
    assert [p.route for p in found] == ["MEA"]


def test_provider_labels_scheduled_positions_as_estimated() -> None:
    provider = RomaGtfsScheduleProvider(Settings.load(), fetch_bytes=lambda url: _zip())
    info = provider.describe()
    assert info.layer == "transit_schedule" and info.synthetic is False
    at = datetime(2026, 11, 13, 7, 5, tzinfo=timezone.utc)
    obs = list(provider.fetch(ROME_BBOX, at, at))
    assert len(obs) == 1 and obs[0].entity_type == "ScheduledVehicle"
    assert obs[0].observed_at == at and obs[0].values == {"scheduledVehicles": 1.0, "routeType": 3.0}
    assert "64" in obs[0].entity_id
