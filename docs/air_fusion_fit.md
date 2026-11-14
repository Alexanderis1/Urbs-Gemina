# Air-quality fusion learned from real data

Data: EEA up-to-date station files for Rome, 01 Jan 2026 to 14 Nov 2026 00:31 UTC, and the CAMS European forecast at each station (Open-Meteo archive). NO2 is hourly; PM10 and PM2.5 are daily means.
Settings are fitted on readings before 2026-09-01 and checked on readings after it (never seen by the fit), by hiding one station at a time and testing the 90% range.

## What was learned

| Layer | CAMS bias: station = a + b x CAMS | CAMS error left (sd) | shared part sd | reach L | local part sd (minus station error) | memory tau |
|---|---|---|---|---|---|---|
| air_no2 | 13.21 + 0.653 x CAMS (station mean 22.76, CAMS mean 14.61) | 10.62 | 7.05 | 12.19 km | 7.94 (8.92 - 4.07) | 7.0 h |
| air_pm10 | 6.98 + 0.807 x CAMS (station mean 22.11, CAMS mean 18.74) | 4.71 | 4.69 | 50.0 km | 0.44 (3.65 - 3.62) | 43.6 h |
| air_pm25 | 3.66 + 0.602 x CAMS (station mean 11.12, CAMS mean 12.38) | 2.9 | 2.8 | 50.0 km | 0.73 (1.99 - 1.85) | 40.8 h |

## Honesty check on held-out months

| Layer | Settings | Status | Coverage of 90% range | Spread of z (1 = honest) | RMSE |
|---|---|---|---|---|---|
| air_no2 | old config, generic prior | calibrated | 97% | 0.8124 | 12.7592 |
| air_no2 | CAMS as is, 50% sigma | uncalibrated | 72% | 1.4135 | 12.3846 |
| air_no2 | **learned** | calibrated | 92% | 0.9629 | 10.5797 |
| air_pm10 | old config, generic prior | uncalibrated | 100% | 0.4603 | 5.0479 |
| air_pm10 | CAMS as is, 50% sigma | calibrated | 97% | 0.7171 | 4.2541 |
| air_pm10 | **learned** | calibrated | 83% | 1.2742 | 4.0266 |
| air_pm25 | old config, generic prior | uncalibrated | 99% | 0.5686 | 3.8585 |
| air_pm25 | CAMS as is, 50% sigma | calibrated | 95% | 0.7713 | 2.8413 |
| air_pm25 | **learned** | calibrated | 84% | 1.2726 | 2.8774 |

## How to read this

- CAMS is a 10 km regional model, so it misses part of the city's own pollution; the bias fit corrects that on average.
- The shared part of the error spreads over the reach L; the local part (a station by a busy road) stays in its own cell.
- A long reach for PM means CAMS is wrong by about the same amount everywhere in the city on a given day.
- Memory tau is how long a reading keeps informing the map when the station goes silent.
