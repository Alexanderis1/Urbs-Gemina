# Scenario kinds for `run_scenario` (what `change` must hold)

Areas: `city`, `municipio:<1-15>`, `zone:<CODE>` or a GeoJSON polygon. Kinds marked heavy refuse areas above the heavy-run limit: propose a smaller area or a polygon around the place.

- `antenna`: `{"action": "add", "site": {"lon", "lat", "height_m", "band": "800|900|1800|2100|3500"}}` (or `eirp_w` instead of `band`). Field P5/P50/P95 and exceedance probability, before and after.
- `population_exposure`: same `change` as `antenna`. Residents and children in census sections above the EMF thresholds, before and after.
- `river_flood`: `{"gauge": "tevere_ripetta", "return_period_years": 200}` (named scenario: the 200-year flood, the official PGRA medium-hazard case; also 50, 100, 500 = the official rare-flood map, which spills over the walls; say "scenario", not forecast), `{"rise_m": 3}` (hypothetical), `{"gauge": "tevere_ripetta", "level_m": 14}`, or `{"gauge": "tevere_ripetta", "forecast_day": "peak"}` (GloFAS forecast). Other gauge: `aniene_lunghezza`.
- `rain_flood`: `{"rain_mm": 60, "duration_h": 1}` (hypothetical) or `{"source": "forecast" | "radar", "duration_h": 3}`; optional `"river": {...}` as in `river_flood` to block the sewer outfalls.
- `chemical_plume`: `{"site": "<Seveso plant name>", "substance": "ammonia", "release_kg_s": 5, "wind": "forecast"}`.
- `heatwave`: `{"temperature": "forecast"}` or `{"tmax_c": 36, "tmin_c": 24}`; what-ifs `"plant_trees": {"cover_added_pct": 10, "where": <area>}` and `"depave": {"impervious_removed_pct": 10, "where": <area>}`.
- `emergency_access` (heavy): `{"service": "ambulance" | "fire" | "police"}` plus one of `"close": {"street": "<name>"}`, `"closed_area": <polygon>`, `"flood": {"kind": "rain_flood", "change": {...}}`.
- `traffic_event` (heavy, synthetic demand): `{"event": {"lon", "lat", "attendees", "radius_m"}}`, `{"close": {"street": "<name>"}}` or `{"roadworks": [...]}`.

Numbers in a `change` are what-if inputs: take them from the officer, or say which default you used. Never present a hypothetical input as a forecast.
