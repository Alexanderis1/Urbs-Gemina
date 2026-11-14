# Scenario engine: validation against real events

Status on 14 Nov 2026 (second pass, early morning). Each scenario model was compared with real past events or official figures where
open data exists. Errors are reported as found. Confidence scores (C, 0-100) say how far a planner can
rely on the numbers. Every result also carries a `calibration` field from `config/scenarios.yaml`, so the
user sees this status in the app.

## Summary

| Scenario | Checked against | Result | C now |
|---|---|---|---|
| River flood (Tiber) | 7 historic floods at Ripetta; official PGRA flood-hazard maps | Water level error 0.5 m (1.2 m on floods left out of the fit). Flood map finds 80 % of the official T200 zone (CSI 0.53). | 60 |
| Rain flood + sewers | 4,577 real flooding call-outs 2013-2022 (Roma Capitale civil protection); reported places in 4 cloudbursts | The pond-and-sewer map has weak street-level skill (AUC 0.54; 16 of 26 places). The new trouble-spot ranking (low ground + past call-outs) scores 0.71 on later years and 0.66-0.86 in all 4 cloudbursts. | 60 (trouble spots), 40 (flood map, street level) |
| Heatwave | 17 Rome weather stations, 184 summer days 2019-2020 (raw hourly data) | Night minimum: error 0.50 °C on stations left out of the fit, against 0.69 °C with no model. Daytime differences between places are not predicted better than the forecast alone. | 65 (nights), 40 (place-to-place by day) |
| Chemical plume | Briggs urban formulas (Hanna 1982); mass conservation; literature accuracy; Britter-McQuaid workbook curves for heavy gases | Formulas match; mass is conserved. Typical Gaussian accuracy: within a factor of 2 about half the time. Heavy gases (chlorine) now get a heavy-gas plume: the deadly zone (AEGL-3) for 5 kg/s of chlorine reaches 0.86 km instead of 0.63 km. | 60 |
| Emergency access | Official Lazio 118 alarm-to-target time (NSG 2023, indicator D09Z) | From the 26 real 118 posts, with call handling and dispatch, the model gives 10.8 min at the 75th percentile against the real 20 min. The gap closes if the nearest post is busy about 3 times in 4. Use it for before/after changes. | 50 (absolute), 60 (changes) |
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

### Second pass: ten years of real call-outs and two more cloudbursts

- **Data.** Roma Capitale's civil-protection event log (DIPPC:300_Eventi_STORICI, 2013-2022) has 4,577
  dated street, home and extended flooding call-outs as points (shared
  `processed/civil_protection_events.geojson`, from the use-cases thread). Two more cloudbursts with
  measured rain and named places were added: 14 Jun 2023 (86 mm at Vigne Nuove, 55 mm at Bufalotta) and
  9 Sep 2024 (over 70 mm at Tor Vergata, over 50 mm in four other areas).
- **The flood map, place by place.** One design storm (40 mm in 1 hour) was run in each municipio. Then
  the test asked whether the real call-outs lie closer to modelled flooding than the centres of
  inhabited census sections do (`scripts/validate_rain_log.py`). Result: 36 % of call-outs within 150 m
  against 30 % for random places, AUC 0.54. That is barely better than chance. There is some skill in the
  north and east (Municipi III, IV, VI, X, XI: AUC 0.57-0.61) and none in the centre (I, V, VII, XII,
  XV). The two new cloudbursts also come out at chance (1 of 4 and 1 of 3 places). Over all four events,
  16 of 26 places were hit.
- **What does predict call-outs.** Ground that sits lower than its surroundings within about 1 km
  (AUC 0.68). Past call-outs within 150 m also predict them: half of the 2018-2022 call-outs had an
  earlier one within 150 m, against a quarter of random places. Flooding in Rome repeats at the same
  low spots, mostly because of blocked or undersized drains that no open map shows.
- **New: trouble spots.** Every rain result now lists `trouble_spots`: the built-up places in the area
  ranked by low ground plus past call-outs, spread at least 300 m apart. Each model hotspot also shows
  `low_ground_m` and `past_call_outs`.

  | Check (all independent of the data used to build the score) | Trouble spots | Flood map |
  |---|---|---|
  | 2018-2022 call-outs, score built from 2013-2017 only | AUC 0.71 | 0.54 |
  | Same, low ground only | AUC 0.68 | |
  | 3 Sep 2024 cloudburst, 11 places vs random streets | AUC 0.76 | 8 of 11 hit |
  | 19 Sep 2011 cloudburst, 8 places | AUC 0.83 | 6 of 8 hit |
  | 14 Jun 2023 cloudburst, 4 places | AUC 0.86 | 1 of 4 hit |
  | 9 Sep 2024 cloudburst, 3 places | AUC 0.66 | 1 of 3 hit |

- **How to use it.** Use trouble spots to choose where to send pumps and patrols first. Use the flood
  map for how much water and how many residents, at district scale, not for single streets.
- **Limits.** Call-outs follow where people live and call, so the ranking also learns where people
  report. The log stops in 2022. The 2023-2024 events have few places. Rain durations of the new events
  are assumptions (2 hours).

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
- **Heavy gases (new).** Gases heavier than air (relative density above 1.1: chlorine 2.49, hydrogen
  sulphide 1.19) now also get a Britter-McQuaid dense plume (HSE workbook 1988, curve fits for every
  alpha band as tabulated by CCPS and Crowl & Louvar). Near the plant the cloud is a low, wide slab that
  slumps and spreads sideways and even a little upwind. Past the workbook's last curve point the diluted
  cloud carries on as an urban passive plume that starts with the slab's width and the same centreline
  value, so there is no jump at the hand-over. The map keeps the larger of the passive and the dense
  value. Tests check the workbook points, the near-field formula and the smooth hand-over.
- **Effect** (5 kg/s of chlorine, wind 3 m/s):

  | Zone | Passive only, P50 reach | With heavy gas, P50 reach | Likely area, passive → heavy |
  |---|---|---|---|
  | AEGL-3 (deadly) | 0.63 km | 0.86 km | 0.02 → 0.10 km² |
  | IDLH | 0.95 km | 1.23 km | 0.04 → 0.13 km² |
  | AEGL-2 (serious) | 2.5 km | 2.9 km | 0.18 → 0.34 km² |

  These reaches are of the same order as published ALOHA runs for a similar chlorine release (about 1 km
  for AEGL-3). The workbook was fitted on flat open ground, so in a built-up city it errs on the safe side.
- **Known limits.** The heavy cloud does not follow slopes, underpasses or the river bed. A side-by-side
  ALOHA run was still not possible because ALOHA is desktop-only software. `dense_gas: false` switches
  the heavy-gas part off.

## Emergency access

- **Reference.** National LEA indicator D09Z: the time from the 118 call to the first vehicle on site,
  75th percentile, red and yellow codes. Lazio: 20 minutes in 2023 and 21 in 2022 (national target 18).
  It covers the whole region, rural areas included, so Rome alone is probably a little faster.
- **Real 118 posts (new).** Ambulances now start from the 26 ARES 118 posts inside Rome, taken from ARES
  118's public list of posts and placed with the city's street-number service
  (`scripts/fetch_ares118_posts.py`, shared `processed/ares118_posts.geojson`). Emergency hospitals are
  used only when that layer is missing.
- **Call handling and dispatch (new).** Legal 118 targets run from the call, so the model now adds the time
  from the call to the ambulance leaving: a median of 4.5 minutes. That is about 1 minute for the 112
  transfer, about 2.4 minutes for 118 call handling and dispatch (Lecce 118 in 2021: 2 min 26 s; Lombardy,
  Citerio 2006: 2.3 min) and about 1 minute for the crew to leave (assumption). `count_from: "departure"`
  gives road time only.
- **Result** (straight line × 1.3 detour at 35 km/h, residents-weighted, 23,591 census sections):

  | Start points | Road time P50 / P75 | Response from the call P50 / P75 | Gap to the real 20 min |
  |---|---|---|---|
  | 22 emergency hospitals (before) | 4.6 / 7.7 min | (not counted before) | 12.3 min |
  | 26 real 118 posts + call handling (now) | 4.1 / 6.3 min | 8.6 / 10.8 min | 9.2 min |

- **What explains the rest: busy ambulances.** If each post is busy with some probability and the first
  free post goes, the 75th percentile becomes:

  | Posts busy | 30 % | 50 % | 70 % | 80 % | 90 % |
  |---|---|---|---|---|---|
  | P75 response | 12.6 | 14.6 | 18.5 | 22.2 | 32.5 min |

  The real 20 minutes matches posts busy about 3 times in 4. That fits Rome's long ambulance waits at
  emergency departments. The model still takes the nearest post as free, so its minutes are a best case.
  The useful signal is the change before and after a closure or flood.
- The road-graph citywide check is still to do: the OpenStreetMap server (Overpass) refused connections
  during the first check.

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

## Weak spots still open (second pass)

1. **Rain, street by street.** The flood map has almost no street-level skill. Trouble spots now cover
   "where first". The real pipe map and blocked-drain reports (AMA / Acea) would fix the cause.
2. **Ambulance minutes.** These are still a best case (a free ambulance at the nearest post). The
   citywide road-graph check is still to do, and the official benchmark is regional, not Rome only.
3. **Heavy gas.** The heavy cloud ignores slopes, underpasses and the Tiber bed. No side-by-side ALOHA run
   has been possible.
4. **Heat by day.** Place-to-place differences by day are no better than the forecast.
5. **River in the centre.** CSI 0.37 inside the walls, and Flaminio floods too early.
6. **Traffic.** SUMO is uncalibrated until the real loop counts arrive.

## Proposed new scenarios

Each uses only real data and models (no simulated sensors). They are listed in order of value for the
city.

1. **Ambulance availability.** What if emergency-department waits drop, or one post gains an ambulance?
   The share of busy posts is the lever: the validation shows it explains most of the gap to the real
   20 minutes. The output is the residents beyond 8 minutes from the call, before and after.
2. **Landslides after heavy rain.** Rain from gauges or radar, on the ISPRA PAI landslide hazard areas
   and the city's landslide-area layer (now being added by the static data thread), would show which
   roads, homes and schools are at risk. The civil-protection log has 66 landslide call-outs to check it
   against.
3. **Earthquake shaking.** An INGV event (webservices.ingv.it, now allowed), with a published Italian
   ground-motion model (Bindi 2011) and census building age, would give the residents in older masonry
   buildings above a shaking level. The log has 3 seismic-damage call-outs, too few to calibrate.
4. **Heatwave plus ozone.** The heatwave run would add the chance of exceeding the 180 µg/m³ ozone
   information threshold from the new `air_o3` belief layer (PR #15). Thresholds live in
   `config/thresholds.yaml`.

## How to rerun

```
PYTHONPATH=. python scripts/validate_rain.py --efficiency 0.15 0.3 0.5 0.8
PYTHONPATH=. python scripts/validate_access.py
PYTHONPATH=. python scripts/validate_heat.py ASTI_DIR   # unzipped Zenodo 19454855
PYTHONPATH=. python scripts/validate_rain_log.py            # add --ranking-only to skip the model runs
PYTHONPATH=. python scripts/fetch_ares118_posts.py
python -m pytest tests/test_scenarios_validation.py
```
