"""Civil Protection rain radar (layer ``rain``). Real, open (CC BY, C=75).

Flow: ask the API for the latest product time, step back in 5-minute frames
through the requested window (at most ``max_frames``), ask ``downloadProduct``
for each frame, and read the GeoTIFF cells inside the bounding box. The API
answers either with a JSON pre-signed link (current API) or the file itself
(older API); both are handled. Every request carries the ``origin`` header the
API requires.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from twin.providers import http
from twin.providers.base import BBox, Observation, ProviderInfo
from twin.providers.raster import read_cells
from twin.providers.settings import Settings, integer, number, text

PROVIDER_ID = "dpc_radar"


def resolve_download(answer: bytes, get: Callable[[str], bytes]) -> bytes:
    """``downloadProduct`` returns JSON with a link, or the GeoTIFF bytes directly."""
    if answer[:1] in (b"{", b"["):
        link = json.loads(answer.decode("utf-8")).get("url")
        if not link:
            raise ValueError("radar API answered without a download url")
        return get(str(link))
    return answer


class DpcRadarProvider:
    def __init__(self, settings: Settings | None = None,
                 http_get_json: Callable[[str], Any] | None = None,
                 http_post: Callable[[str, dict[str, Any]], bytes] | None = None,
                 http_get: Callable[[str], bytes] | None = None) -> None:
        settings = settings or Settings.load()
        self._config = settings.section("open", PROVIDER_ID)
        self._api = text(self._config, "api_url", "https://radar-api.protezionecivile.it").rstrip("/")
        self._product = text(self._config, "product", "SRI")
        headers = {"origin": text(self._config, "origin", "https://radar.protezionecivile.it")}
        timeout = number(self._config, "timeout_s", 60.0)
        self._get_json = http_get_json or (lambda url: http.get_json(url, headers, timeout))
        self._post = http_post or (lambda url, body: http.post_json(url, body, headers, timeout))
        self._get = http_get or (lambda url: http.get_bytes(url, timeout_s=timeout))
        self._step = timedelta(minutes=integer(self._config, "step_minutes", 5))
        self._max_frames = integer(self._config, "max_frames", 12)
        self._rel_sigma = number(self._config, "relative_sigma", 0.5)

    def describe(self) -> ProviderInfo:
        return ProviderInfo(
            id=PROVIDER_ID,
            kind="open",
            layer="rain",
            licence="CC BY (Dipartimento della Protezione Civile), C=75",
            cadence="5 min",
            synthetic=False,
            notes=f"Product {self._product} (surface rainfall intensity, mm/h). Credit: Dipartimento della Protezione Civile.",
        )

    def latest(self) -> datetime:
        answer = self._get_json(f"{self._api}/findLastProductByType?type={self._product}")
        millis = int(answer["lastProducts"][0]["time"])
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)

    def frames(self, start: datetime, end: datetime) -> list[datetime]:
        """Frame times in the window, newest first, never later than the latest product."""
        newest = min(_aware(end), self.latest())
        out: list[datetime] = []
        moment = newest
        while moment >= _aware(start) and len(out) < self._max_frames:
            out.append(moment)
            moment -= self._step
        return out

    def fetch(self, bbox: BBox, start: datetime, end: datetime) -> Iterator[Observation]:
        for frame in self.frames(start, end):
            millis = int(frame.timestamp() * 1000)
            answer = self._post(f"{self._api}/downloadProduct", {"productType": self._product, "productDate": millis})
            tiff = resolve_download(answer, self._get)
            source = f"{PROVIDER_ID}@{self._product}-{frame.strftime('%Y%m%dT%H%MZ')}"
            for cell in read_cells(tiff, bbox):
                if cell.value < 0.0:
                    continue
                yield Observation(
                    entity_id=f"urn:ngsi-ld:WeatherObserved:dpc-radar-r{cell.row}-c{cell.col}",
                    entity_type="WeatherObserved",
                    lon=cell.lon,
                    lat=cell.lat,
                    observed_at=frame,
                    values={"precipitation": round(cell.value, 2)},
                    sigma={"precipitation": round(max(0.1, self._rel_sigma * cell.value), 2)},
                    source_id=source,
                    synthetic=False,
                )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
