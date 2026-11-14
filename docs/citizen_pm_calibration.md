# Citizen PM sensors calibrated against official stations

5 Sensor.Community nodes in Rome, daily means 2026-08-15 to 2026-11-12 (archive.sensor.community, ODbL). Reference: mean of the EEA stations in Rome that day. Model: raw = s x reference x (1 + c x RH/(100 - RH)), RH capped at 95 %. Scores leave one sensor out.

| Pollutant | Sensor-days | Sensors | Dry scale s | Growth c | Raw error (RMSE) | Corrected error (RMSE) | Corrected bias | Relative error |
|---|---|---|---|---|---|---|---|---|
| pm10 | 306 | 4 | 0.527 | 0.01 | 11.47 | 11.59 | 1.08 | 43% |
| pm25 | 306 | 4 | 0.488 | 0.01 | 5.34 | 6.56 | 0.92 | 59% |

How it is used: the live provider (twin/providers/open/sensor_community.py) divides every reading by the dry scale s and gives it the relative error above, doubled at humidity >= 80 %. The humidity growth term is not applied when it comes out near zero, as it does on daily means. Rescaling removes the bias (sensors read about half the official level), which matters most in the map because a bias is shared by all citizen sensors while their noise averages out; the error per reading stays large, so the stations still dominate the PM layers.
