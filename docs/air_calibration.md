# Air-quality uncertainty check on real EEA stations

Window 2026-11-10 23:05 to 2026-11-13 23:05 UTC, 838 hourly readings from 13 EEA stations in Rome (unverified up-to-date data). Method: leave one station out, predict it from the prior plus the others, check the 90% range.

| Layer | Status | Held-out predictions | Coverage of 90% range | Spread of z | RMSE | Reason |
|---|---|---|---|---|---|---|
| air_no2 | calibrated | 799 | 95% | 0.8279 | 13.8174 | 799 held-out readings: coverage 95%, error spread 0.83 |
| air_pm10 | uncalibrated | 24 | 100% | 0.4993 | 4.9375 | coverage of the 90% range is 100%, outside 80%-97%; spread of standardised errors is 0.50, outside 0.7-1.4 |
| air_pm25 | uncalibrated | 15 | 100% | 0.8548 | 5.3678 | coverage of the 90% range is 100%, outside 80%-97% |

```json
{
  "stations": 13,
  "readings": 838,
  "results": {
    "air_no2": {
      "status": "calibrated",
      "reason": "799 held-out readings: coverage 95%, error spread 0.83",
      "n_predictions": 799,
      "coverage": 0.9524,
      "z_mean": -0.4381,
      "z_sd": 0.8279,
      "rmse": 13.8174
    },
    "air_pm10": {
      "status": "uncalibrated",
      "reason": "coverage of the 90% range is 100%, outside 80%-97%; spread of standardised errors is 0.50, outside 0.7-1.4",
      "n_predictions": 24,
      "coverage": 1.0,
      "z_mean": -0.0276,
      "z_sd": 0.4993,
      "rmse": 4.9375
    },
    "air_pm25": {
      "status": "uncalibrated",
      "reason": "coverage of the 90% range is 100%, outside 80%-97%",
      "n_predictions": 15,
      "coverage": 1.0,
      "z_mean": -0.2707,
      "z_sd": 0.8548,
      "rmse": 5.3678
    }
  }
}
```
