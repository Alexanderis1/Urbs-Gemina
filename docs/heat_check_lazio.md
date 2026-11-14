# Heatwave model checked on Regione Lazio thermometers

Independent data: 12 Civil Protection thermometers in Rome (Regione Lazio open data, CC BY 4.0), daily minimum and maximum, June-August 2018-2026 (some months missing on the portal). The model was fitted on 17 ASTI rooftop stations in 2019-2020, so this is a test on another network and other years.

| Quantity | Days | No model | Engine coefficients (fitted on ASTI) | Re-fitted here, station left out |
|---|---|---|---|---|
| night minimum, all summer days | 306 | 2.239 °C | 1.826 °C | 1.868 °C |
| night minimum, hot days | 185 | 2.303 °C | 1.891 °C | 1.934 °C |
| day maximum, all summer days | 306 | 1.623 °C | 1.637 °C | 2.045 °C |
| day maximum, hot days | 185 | 1.722 °C | 1.737 °C | 2.18 °C |

Re-fitted coefficients (°C from 0 to 100 %):

- night_minimum/all_summer_days: {'impervious_city': 4.89, 'impervious': 1.01, 'trees': 5.57} (engine: {'impervious_city': 2.9, 'impervious': 0.6, 'trees': 1.2})
- night_minimum/hot_days: {'impervious_city': 4.91, 'impervious': 1.23, 'trees': 5.8} (engine: {'impervious_city': 2.9, 'impervious': 0.6, 'trees': 1.2})
- day_maximum/all_summer_days: {'impervious_city': 0.5, 'impervious': 1.03, 'trees': -6.49} (engine: {'impervious_city': 0.0, 'impervious': 0.0, 'trees': 0.3})
- day_maximum/hot_days: {'impervious_city': 0.34, 'impervious': 1.59, 'trees': -7.73} (engine: {'impervious_city': 0.0, 'impervious': 0.0, 'trees': 0.3})

Stations and their sealing (100 m cell, 2.2 km district):

- Collegio Romano: 97% / 77%
- Fosso di Pantanello ad Ostia: 0% / 7%
- Massimina: 8% / 14%
- Osteria Nuova: 5% / 6%
- Roma EUR: 60% / 31%
- Roma Flaminio: 88% / 47%
- Roma Macao: 81% / 80%
- Roma Monte Mario: 38% / 37%
- Roma Sud: 72% / 61%
- Salone: 0% / 12%
- Tevere a Castelgiubileo: 26% / 26%
- Tor Vergata: 0% / 33%

Positions: Roma Capitale Civil Protection plan (2018), Tab. 8. Stations differ in height above sea level (up to about 130 m at Monte Mario), which the model does not use.
