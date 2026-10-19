# Dataset Declaration

**Track:** Air quality (PM2.5, Pakistan)

**Primary user and decision:** Provincial EPA officer deciding when to issue smog warnings.

**Source 1:** OpenAQ, hourly PM2.5 from Pakistani stations. Publisher: OpenAQ. URL: https://openaq.org. Licence: varies per data provider (recorded per file in manifest.csv). Updates hourly.

**Source 2:** Open-Meteo Historical Weather API, hourly temperature, humidity, wind, pressure, precipitation. Publisher: Open-Meteo. URL: https://open-meteo.com. Licence: CC BY 4.0 (non-commercial free tier). Updates hourly.

**Source not on the track list:** Open-Meteo. Weather is not on the air quality track list. Credible because it serves reanalysis and weather model data from national weather services (check and name the exact data source on their docs page).

**Expected volume:** TODO (fill after the station check), target 50,000+ hourly rows.

**Why this data fits:** PM2.5 is the standard smog measure, and weather drives it (wind, humidity, temperature).

**Baseline (fixed before any results):** PM2.5 = same hour yesterday. Metric: MAE on a held-out final time period.