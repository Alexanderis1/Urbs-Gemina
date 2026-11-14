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
| Heatwave | Published Rome measurements: 17 stations (2019-2020) and bus-mounted sensors | Coefficients changed to match: nights +3.5 °C on fully sealed ground, small day contrasts. Not yet re-fitted on the raw station files. | 60 |
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

- **References.** Cecilia et al. 2022 (Urban Climate 47:101355) used 17 Rome stations in summers 2019-2020.
  Temperature rises linearly with Copernicus imperviousness. The night heat island is 3.4 °C, and the
  correlation is 0.81 with the daily minimum but only 0.17 with the maximum. Cecilia et al. 2026 (Urban
  Climate 102832) used bus-mounted sensors over 53 summer days. The night difference between fully
  sealed and natural ground is 3.6 °C. The sea breeze removes daytime contrasts. Tree cover cools only in
  the early morning, up to 0.5 °C for 40 % cover.
- **Changes.** The old coefficients made days too contrasted (+2 °C for sealed ground, -4 °C for full tree
  cover). They are now:
  - night: sealed ground +3.5 ± 0.5 °C, trees -1.2 ± 0.6 °C;
  - day: +0.5 ± 0.5 °C and -0.5 ± 0.5 °C.

  Tree-planting what-ifs now also report night cooling and the residents who no longer have tropical
  nights, because that is where trees and de-paving matter in Rome.
- **Still to do.** The raw hourly data of the 17 stations is open on Zenodo (record 19454855). This session
  could not download it (approval needed), so the coefficients are not yet re-fitted on it. Sensor.Community
  has only 2 Rome temperature sensors; the ARPA Lazio and Meteostat archives are not reachable from here.

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

## How to rerun

```
PYTHONPATH=. python scripts/validate_rain.py --efficiency 0.15 0.3 0.5 0.8
PYTHONPATH=. python scripts/validate_access.py
python -m pytest tests/test_scenarios_validation.py
```
