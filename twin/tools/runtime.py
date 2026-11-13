"""Everything a tool needs at run time, built once per process."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Protocol

from twin.providers.base import Provider, ProviderNotConfigured
from twin.providers.registry import FACTORIES
from twin.tools.context_check import distance_to_geometry_m
from twin.tools.envelope import Source, make_envelope, utc_now
from twin.tools.geocode import Nominatim
from twin.tools.layers import LayerStore
from twin.tools.settings import Settings, default_settings


@dataclass(frozen=True)
class BaselineValue:
    value_v_per_m: float
    source: Source
    distance_m: float


class BaselineSource(Protocol):
    """Official EMF estimate at a point (Cartoradio), or ``None`` where there is none."""

    def at(self, lon: float, lat: float) -> BaselineValue | None: ...


class ProviderBaseline:
    """Adapts the ``emf_baseline`` provider (WS3) to :class:`BaselineSource`."""

    def __init__(self, provider: Provider, value_keys: list[str], search_radius_m: float) -> None:
        self.provider = provider
        self.value_keys = value_keys
        self.radius_m = search_radius_m

    def at(self, lon: float, lat: float) -> BaselineValue | None:
        d_lat = self.radius_m / 111_195.0
        d_lon = d_lat / max(0.2, abs(math.cos(math.radians(lat))))
        now = datetime.now(timezone.utc)
        best: tuple[float, float, str] | None = None
        for obs in self.provider.fetch((lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat),
                                       now - timedelta(days=3650), now):
            key = next((k for k in self.value_keys if k in obs.values), None)
            if key is None:
                continue
            distance = distance_to_geometry_m(lon, lat, {"type": "Point", "coordinates": [obs.lon, obs.lat]})
            if distance <= self.radius_m and (best is None or distance < best[0]):
                best = (distance, obs.values[key], obs.source_id)
        if best is None:
            return None
        info = self.provider.describe()
        return BaselineValue(value_v_per_m=best[1], distance_m=best[0],
                             source=Source(id=best[2] or info.id, retrieved_at=utc_now()))


@dataclass
class ToolRuntime:
    settings: Settings
    store: LayerStore
    geocoder: Nominatim | None = None
    baseline: BaselineSource | None = None
    providers: dict[str, Provider] = field(default_factory=dict)

    @classmethod
    def default(cls, settings: Settings | None = None) -> "ToolRuntime":
        settings = settings or default_settings()
        store = LayerStore(raw_dir=settings.paths.raw, manifest_path=settings.paths.manifest,
                               processed_dir=settings.paths.data / "processed")
        geo = settings.tools.get("geocoder", {})
        geocoder = Nominatim(base_url=str(geo.get("nominatim_url", "https://nominatim.openstreetmap.org/search")),
                             user_agent=str(geo.get("user_agent", "urbs-gemina/0.1")),
                             timeout_s=float(geo.get("timeout_s", 10)), max_results=int(geo.get("max_results", 3)))
        runtime = cls(settings=settings, store=store, geocoder=geocoder)
        runtime.providers = runtime._build_providers()
        layer = str(settings.tool("estimate_field", "baseline_layer"))
        if layer in runtime.providers and runtime.simulation_allowed(layer, runtime.providers[layer]):
            runtime.baseline = ProviderBaseline(runtime.providers[layer],
                                                list(settings.tool("estimate_field", "baseline_value_keys")),
                                                float(settings.tool("estimate_field", "baseline_search_radius_m")))
        return runtime

    def simulation_allowed(self, layer: str, provider: Provider) -> bool:
        """False when the provider generates data for a layer that must not be simulated."""
        try:
            synthetic = provider.describe().synthetic
        except ProviderNotConfigured:
            return True
        return not synthetic or layer in self.settings.tools.get("allowed_simulated_layers", [])

    def envelope(self, tool: str, inputs: Mapping[str, Any], result: Any, data_kinds: Mapping[str, str],
                 sources: Iterable[Source] = (), warnings: Iterable[str] = (), **kwargs: Any) -> dict[str, Any]:
        """Tool envelope with this runtime's config hashes in the run id."""
        return make_envelope(tool, inputs, result, data_kinds, sources, warnings,
                             config_hashes=self.settings.config_hashes(), **kwargs)

    def _build_providers(self) -> dict[str, Provider]:
        active: dict[str, Provider] = {}
        for layer, provider_id in self.settings.providers.items():
            factory = FACTORIES.get(provider_id)
            if factory is None:
                continue
            try:
                active[layer] = factory()
            except ProviderNotConfigured:
                continue
        return active
