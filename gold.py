import duckdb, pandas as pd
from config import *

def season(m):
    return "winter" if m in (11, 12, 1, 2) else "pre_monsoon" if m <= 6 else "monsoon" if m <= 9 else "post_monsoon"

def build_gold(run_id):
    GOLD.mkdir(parents=True, exist_ok=True)
    pm = pd.read_parquet(CLEANED / "pm25.parquet")
    wx = pd.read_parquet(CLEANED / "weather.parquet")
    st = pd.read_csv(DATA / "stations.csv")[["station_id", "name", "city"]]
    g = pm.merge(wx, on=["station_id", "ts"], how="left").merge(st, on="station_id", how="left")
    g = g.sort_values(["station_id", "ts"]).reset_index(drop=True)   # hourly grid per station, so shift(24) = 24h ago
    by = g.groupby("station_id")["pm25"]
    for k in (24, 48, 168):
        g[f"pm25_lag{k}"] = by.shift(k)
    g["pm25_roll24"] = by.transform(lambda s: s.shift(24).rolling(24, min_periods=12).mean())
    loc = g["ts"].dt.tz_convert("Asia/Karachi")
    g["hour"], g["dow"], g["month"] = loc.dt.hour, loc.dt.dayofweek, loc.dt.month
    g["season"] = g["month"].map(season)
    out = GOLD / "pm25_gold.parquet"
    g.to_parquet(out, index=False)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute(f"CREATE OR REPLACE TABLE gold_pm25 AS SELECT * FROM read_parquet('{out.as_posix()}')")
    con.close()
    print(f"gold rows: {len(g)}, with target: {g.pm25.notna().sum()}")