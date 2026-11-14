# Air-quality fusion learned from real data

Data: EEA up-to-date station files for Rome, 01 Jan 2026 to 14 Nov 2026 04:18 UTC, and the CAMS European forecast at each station (Open-Meteo archive). NO2 and O3 are hourly; PM10 and PM2.5 are daily means.
Settings are fitted on readings before 2026-09-01 and checked on readings after it (never seen by the fit), by hiding one station at a time and testing the 90% range.

## What was learned

| Layer | CAMS bias: station = a + b x CAMS | CAMS error left (sd) | shared part sd | reach L | local part sd (minus station error) | memory tau |
|---|---|---|---|---|---|---|
| air_no2 | 13.61 + 0.624 x CAMS (station mean 22.76, CAMS mean 14.61) | 9.26 | 5.7 | 41.28 km | 7.3 (8.36 - 4.07) | 4.9 h |
| air_pm10 | 6.98 + 0.807 x CAMS (station mean 22.11, CAMS mean 18.74) | 4.69 | 4.69 | 50.0 km | 0.0 (3.65 - 4.4) | 43.6 h |
| air_pm25 | 3.66 + 0.602 x CAMS (station mean 11.12, CAMS mean 12.38) | 2.8 | 2.8 | 50.0 km | 0.0 (1.99 - 3.11) | 40.8 h |
| air_o3 | 3.99 + 0.798 x CAMS (station mean 56.63, CAMS mean 65.93) | 13.26 | 13.0 | 26.33 km | 2.6 (9.98 - 9.64) | 6.9 h |

## Honesty check on held-out months

| Layer | Settings | Status | Coverage of 90% range | Spread of z (1 = honest) | RMSE |
|---|---|---|---|---|---|
| air_no2 | no map, one city-wide value | calibrated | 96% | 0.8026 | 11.3599 |
| air_no2 | CAMS as is, 50% sigma | uncalibrated | 73% | 1.4645 | 11.4077 |
| air_no2 | **learned** | calibrated | 90% | 0.969 | 9.3461 |
| air_pm10 | no map, one city-wide value | calibrated | 97% | 0.7706 | 3.9264 |
| air_pm10 | CAMS as is, 50% sigma | calibrated | 94% | 0.8392 | 3.8354 |
| air_pm10 | **learned** | calibrated | 93% | 0.8856 | 3.7698 |
| air_pm25 | no map, one city-wide value | uncalibrated | 97% | 0.6975 | 2.9571 |
| air_pm25 | CAMS as is, 50% sigma | calibrated | 97% | 0.7019 | 2.7478 |
| air_pm25 | **learned** | calibrated | 95% | 0.768 | 2.7421 |
| air_o3 | no map, one city-wide value | uncalibrated | 100% | 0.4567 | 14.1618 |
| air_o3 | CAMS as is, 50% sigma | uncalibrated | 99% | 0.5226 | 12.1158 |
| air_o3 | **learned** | calibrated | 87% | 1.1669 | 12.5047 |

## Land-use term for air_no2

Covariate: motor road length within 100 m (Overture roads). Slope 1.20 ug/m3 per 100 m of road, centred on the station mean (607.2 m). The stations' lasting differences from the corrected CAMS have a spread of 6.39 ug/m3; predicting each station from a slope fitted on the others leaves 3.7 ug/m3.

| Station | Road within 100 m (m) | Lasting offset (ug/m3) |
|---|---|---|
| IT0825A | 1333.8 | 13.24 |
| IT0828A | 660.2 | 7.04 |
| IT0952A | 0.0 | -8.16 |
| IT0953A | 0.0 | -7.48 |
| IT0956A | 322.2 | -3.27 |
| IT0957A | 0.0 | -7.61 |
| IT1176A | 1055.0 | 0.74 |
| IT1834A | 624.1 | 3.18 |
| IT1835A | 1059.6 | -0.84 |
| IT1836A | 690.7 | 1.45 |
| IT1837A | 1232.0 | 6.36 |
| IT1906A | 637.6 | 2.61 |
| IT2012A | 279.0 | -7.38 |

Before this upgrade the live NO2 layer had a held-out RMSE of 12.8 ug/m3 (fixed guesses: reach 3 km, memory 3 h, no bias correction; first run of this script on 14 Nov 2026).

## How to read this

- CAMS is a 10 km regional model, so it misses part of the city's own pollution; the bias fit corrects that on average.
- The shared part of the error spreads over the reach L; the local part (a station by a busy road) stays in its own cell.
- A long reach for PM means CAMS is wrong by about the same amount everywhere in the city on a given day.
- Memory tau is how long a reading keeps informing the map when the station goes silent.
