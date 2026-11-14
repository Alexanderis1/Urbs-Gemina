# Scenario engine: validation against real events

Status on 14 Nov 2026. Each scenario model was compared with real past events or official figures where
open data exists. Errors are reported as found. Confidence scores (C, 0-100) say how far a planner can
rely on the numbers. Every result also carries a `calibration` field from `config/scenarios.yaml`, so the
user sees this status in the app.

## Summary

| Scenario | Checked against | Result | C now |
|---|---|---|---|
| River flood (Tiber) | 7 historic floods at Ripetta; official PGRA flood-hazard maps | Water level error 0.5 m (1.2 m on floods left out of the fit). Flood map finds 80 % of the official T200 zone (CSI 0.53). | 60 |
| Rain flood + sewers | Reported flooded streets in the 3 Sep 2024 and 19 Sep 2011 cloudbursts | 14 of 19 reported places flooded in the model, against 33-52 % for random streets. Sewer efficiency set to 0.3 from a sweep. | 50 |
| Heatwave | 17 Rome weather stations, 184 summer days 2019-2020 (raw hourly data) | Night minimum: error 0.50 °C on stations left out of the fit, against 0.69 °C with no model. Daytime differences between places are not predicted better than the forecast alone. | 65 (nights), 40 (place-to-place by day) |
| Chemical plume | Briggs urban formulas (Hanna 1982); mass conservation; literature accuracy | Formulas match; mass is conserved. Typical Gaussian accuracy: within a factor of 2 about half the time. Heavy gases (chlorine) flagged for ALOHA. | 55 |
| Emergency access | Official Lazio 118 alarm-to-target time (NSG 2023, indicator D09Z) | The model is about 12 minutes faster than real responses at the 75th percentile, because it leaves out call handling and ambulance availability. Use it for before/after changes, not absolute times. | 40 (absolute), 55 (changes) |
| Traffic (SUMO) | Not checked here: needs the real traffic loops from the providers thread | |

## River flood

- **Rating curve (level from discharge) at Ripetta.** It was a straight line that overshot big floods
  (T200 at 19.3 m). It is now a power law fitted on 7 historic peak pairs (`eval/scenarios/tiber_ripetta_peaks.json`):
  level = 5.89 + (Q / 198.76)^(1/1.1475). Fit error (RMSE) 0.50 m. Leave-one-out error 1.19 m, against
  1.43 m for the old line.
- **Flood maps vs PGRA** (official hazard zones, within 2 km of the Tiber):

  | Case | Hit rate | False alarms | CSI |
  |---|---|---|---|
  | T50 vs P3 | | | 0.50 |
  | T200 vs P3+P2, before | 0.57 | 0.22 | 0.49 |
  | T200 vs P3+P2, now | 0.80 | 0.38 | 0.53 |
  | T500 vs all classes | | | 0.52 |

  By reach at T200: north of the city CSI 0.78, the walled centre 0.37, the south towards the sea 0.33
  (it was 0.06 before the river level was tapered along the river towards the mouth).
- **Known error.** Inside the walls the model starts flooding Flaminio / Foro Italico at about 3100 m³/s,
  where PGRA puts only the rare T500 zone. The Ostiense patch matches PGRA P3. Literature puts the start of
  flooding in Rome near T175 (about 3300 m³/s; Fiori 2023).

## Rain flood + sewers

- **Method.** For each event the model ran with the reported rain per municipio. A reported place is a
  hit when modelled flooding (P50 ponding or P50 sewer surcharge) is within 150 m. Places come from news
  and Roma Capitale reports and are located with the city's street-number service. The same test on 60
  random streets per municipio gives the chance rate. Script: `scripts/validate_rain.py`.
- **Sweep of sewer efficiency** (share of the design capacity that works in a real storm):

  | Efficiency | 2024 hits | 2024 chance | 2011 hits | 2011 chance |
  |---|---|---|---|---|
  | 0.15 | 0.91 | 0.76 | 1.00 | 0.69 |
  | **0.3** | **0.73** | **0.52** | **0.75** | **0.33** |
  | 0.5 | 0.45 | 0.38 | 0.75 | 0.33 |
  | 0.8 | 0.36 | 0.35 | 0.75 | 0.33 |

  0.3 gives the largest gain over chance in both events, so it stays. A 10 mm/h shower floods under
  0.1 km² per municipio (dry check).
- **Known errors.** The sample is small (19 places). The 2011 result is clearly better than chance (p = 0.02).
  The 2024 result is not yet (p = 0.14). The misses are three suburban junctions (Casilina at
  Borghesiana, Tor Bella Monaca at Casilina, Prenestina at Togliatti). They are probably blocked drains or
  underpasses that the 20 m terrain does not show. Half of random streets have modelled flooding within
  150 m in a 60 mm/h storm, so the map is broad. Use the hotspot ranking, not single streets.

## Heatwave

- **Data.** ASTI-Network, 17 rooftop weather stations across Rome, hourly, June to August 2019 and 2020
  (Cecilia et al., CNR-ISAC; Zenodo 19454855, CC BY 4.0). Downloaded with Alessandro's approval on
  14 Nov 2026. Daily maximum and minimum per station are in the shared
  `processed/asti_stations_daily.csv`. Script: `scripts/validate_heat.py`, results in
  `eval/scenarios/heat_validation.json`.
- **Method.** On each of 184 days (75 hot days, with a station average above 32 °C), every station's
  daily maximum and minimum is compared with the average of all stations. Each model reading is fitted,
  then scored on each station left out in turn. "No model" means every station equals the average.
- **Main finding: Rome's warm nights come from the sealing of the whole district, not of the block.**

  | Night minimum, error on unseen stations | All days | Hot days |
  |---|---|---|
  | No model | 0.69 °C | 0.73 °C |
  | Old model (local differences only) | 1.01 °C | 1.03 °C |
  | Sealing at the 100 m cell only | 0.59 °C | 0.63 °C |
  | **New model (district + local)** | **0.50 °C** | **0.55 °C** |

  The district term is about 2.9 °C for a fully sealed 2.2 km area, close to the 3.4 °C published from
  the same stations. The extra effect of the block itself is only about 0.6 °C.
- **The forecast carries no heat island.** On 14 Nov 2026 the ICON-2I forecast put Porta Maggiore
  (80 % sealed) only 0.1-0.3 °C warmer at night than the Appia Antica park. The stations show about 2 °C in
  summer. So the model now adds the district term on top of the forecast. If a future forecast includes
  the city's heat island, this term must be switched off to avoid counting it twice.
- **Daytime.** No reading beats "every station equals the average" (0.56 °C). The sea breeze evens
  out the afternoon, as the 2026 bus-sensor study also found. Day terms are now near zero, so the hot-day
  map follows the forecast, and its place-to-place detail should not be trusted.
- **Trees.** Rooftop stations cannot see street-level shade. The tree term keeps the street-level value
  from the bus-sensor study: about 0.5 °C cooler at dawn for 40 % canopy, 1.2 °C at full cover. A
  tree-planting what-if now reports night cooling and the residents who no longer have tropical nights.
- **Limits.** All 17 stations are on rooftops; street level is usually warmer by day. There are two
  summers, and the stations were also used to choose the coefficients. The left-out score is the honest one.

## Chemical plume

- The dispersion widths follow the Briggs urban curves (Hanna 1982 form). A test checks that the mass
  crossing a plane downwind equals the release.
- **Accuracy.** Gaussian plume models typically get within a factor of 2 of measured concentrations about
  half the time (FAC2 about 0.5; Hanna and Chang 2012). Every run states this.
- **Dense gas.** Gases heavier than air (relative density above 1.1: chlorine 2.49, hydrogen sulphide 1.19)
  get a warning to check with a heavy-gas model such as ALOHA. A side-by-side ALOHA run was not possible
  because ALOHA is desktop-only software.

## Emergency access

- **Reference.** National LEA indicator D09Z: the time from the 118 call to the first vehicle on site,
  75th percentile, red and yellow codes. Lazio: 20 minutes in 2023 and 21 in 2022 (national target 18).
- **Model.** The run used the model's own rule from the nearest of 22 emergency hospitals to each of
  23,591 census sections (2.75 M residents), weighted by residents. It used the straight line × 1.3
  detour, at 35 km/h (50 km/h cap × 0.7). The road-graph run could not be used because the OpenStreetMap
  server (Overpass) refused connections during the check. Result: travel time P50 4.6 min, P75 7.7 min,
  P95 16.1 min (`eval/scenarios/access_validation.json`).
- **Reading.** The model's P75 is about 12 minutes below the real one. The gap comes from:
  - call handling and dispatch;
  - ambulances that are busy elsewhere and not at a hospital;
  - traffic;
  - real 118 posts, which differ from hospitals.

  Every ambulance run now shows the real 20-minute figure. Its absolute minutes should be read as a best
  case. The useful signal is the change before and after a closure or flood.

## Traffic

Not checked in this pass. Calibrating SUMO needs the real traffic loop counts, which the providers thread
supplies (traffic loops are the only simulated sensors allowed).

## Physics from the physics thread (PR #13)

- **Antenna and population exposure.** Near the changed sites (600 m), the field now comes from
  `twin/physics`:
  - the 3GPP sector pattern;
  - diffraction over the LiDAR-height city model;
  - building entry loss indoors;
  - Sionna ray-traced maps where a site has been traced (within 290 m).

  Beyond that, and whenever `twin/physics` is not installed, the model falls back to free space, which
  is a worst case. At the traced test site (1800 MHz, 30 m) the highest street-level value went from
  8.6 V/m (free space) to 1.0 V/m. The physics thread measured the CPU engine within +1.5 dB (median) of
  ray tracing.
- **Floods** already read the physics thread's bare-earth terrain (`dtm_glo30_ground.tif`) and the LiDAR
  wall crests (130 points, Ponte Milvio to Ponte Marconi).
- **Heatwave.** PR #13 has no heat physics. The heat model now rests on the station fit above.

## How to rerun

```
PYTHONPATH=. python scripts/validate_rain.py --efficiency 0.15 0.3 0.5 0.8
PYTHONPATH=. python scripts/validate_access.py
PYTHONPATH=. python scripts/validate_heat.py ASTI_DIR   # unzipped Zenodo 19454855
python -m pytest tests/test_scenarios_validation.py
```
