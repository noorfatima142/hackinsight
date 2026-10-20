import csv, hashlib, json
import pandas as pd
try:
    import pandera.pandas as pa
except ImportError:
    import pandera as pa
from pandera.errors import SchemaErrors
from config import *

QCOLS = ["run_id", "ts_utc", "table", "station_id", "rule", "action", "rows_affected", "rows_total", "detail"]
WX_VARS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
           "surface_pressure", "precipitation"]
RANGES = {"temperature_2m": (-30, 55), "relative_humidity_2m": (0, 100), "wind_speed_10m": (0, 150),
          "wind_direction_10m": (0, 360), "surface_pressure": (600, 1100), "precipitation": (0, 300)}

def log(run_id, table, rule, action, n, total, station_id="", detail=""):
    assert action in ("fix", "fill", "flag", "pass")
    if int(n) == 0 and action != "pass": return
    new = not QUALITY_LOG.exists()
    with open(QUALITY_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(QCOLS)
        w.writerow([run_id, pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), table, station_id,
                    rule, action, int(n), int(total), detail])

def validate(schema, df, run_id, table):
    try:
        schema.validate(df, lazy=True)
        log(run_id, table, "pandera_schema", "pass", len(df), len(df))
    except SchemaErrors as e:
        log(run_id, table, "pandera_schema_failed", "flag", len(e.failure_cases), len(df),
            detail=str(e.failure_cases.head(3).to_dict("records"))[:300])
        raise

UTC_CHECK = pa.Check(lambda s: str(s.dt.tz) == "UTC")
PM_SCHEMA = pa.DataFrameSchema({
    "station_id": pa.Column(int, coerce=True),
    "ts": pa.Column(checks=UTC_CHECK, nullable=False),
    "pm25": pa.Column(float, pa.Check.in_range(0, 1000), nullable=True),
    "is_filled": pa.Column(bool), "is_flagged": pa.Column(bool),
    "row_id": pa.Column(str, unique=True)}, unique=["station_id", "ts"])
WX_SCHEMA = pa.DataFrameSchema({
    "station_id": pa.Column(int, coerce=True),
    "ts": pa.Column(checks=UTC_CHECK, nullable=False),
    **{v: pa.Column(float, pa.Check.in_range(*RANGES[v]), nullable=True) for v in WX_VARS}},
    unique=["station_id", "ts"])

def row_ids(sid, idx):
    return [hashlib.sha1(f"{sid}|{t.isoformat()}".encode()).hexdigest()[:16] for t in idx]

def load_pm25(run_id):
    recs = []
    for p in (RAW / "openaq").glob("s*.json"):
        sid, m = int(p.name.split("_")[0][1:]), p.stat().st_mtime
        for r in json.loads(p.read_text()):
            t = ((r.get("period") or {}).get("datetimeFrom") or {}).get("utc")
            if t is not None and r.get("value") is not None:
                recs.append((sid, t, float(r["value"]), m))
    if not recs:
        raise RuntimeError("No parsable OpenAQ rows. Send me the first record of one file in data/raw/openaq.")
    df = pd.DataFrame(recs, columns=["station_id", "ts", "pm25_raw", "fetched"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.floor("h")
    df = df.sort_values("fetched"); n = len(df)
    df = df.drop_duplicates(["station_id", "ts"], keep="last")
    log(run_id, "pm25", "drop_duplicate_station_hour (keep latest fetch)", "fix", n - len(df), n)
    return df.drop(columns="fetched")

def clean_pm25(run_id):
    df, out = load_pm25(run_id), []
    for sid, g in df.groupby("station_id"):
        g = g.set_index("ts").sort_index()
        g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="h")); g.index.name = "ts"
        n, raw = len(g), g["pm25_raw"]
        bad = (raw < 0) | (raw > 1000)
        v = raw.mask(bad)
        log(run_id, "pm25", "value_outside_0_1000", "flag", bad.sum(), n, sid, "set to NaN, original in pm25_raw")
        runs = (v != v.shift()).cumsum()
        stuck = v.notna() & (v.groupby(runs).transform("size") >= 24)
        v = v.mask(stuck)
        log(run_id, "pm25", "identical_value_24h_or_more (stuck sensor)", "flag", stuck.sum(), n, sid, "set to NaN")
        miss = v.isna()
        glen = miss.groupby((miss != miss.shift()).cumsum()).transform("size")
        short = miss & (glen <= FILL_MAX_HOURS)
        interp = v.interpolate(limit_area="inside")
        filled = short & interp.notna()
        v = v.mask(filled, interp)
        log(run_id, "pm25", f"gap_le_{FILL_MAX_HOURS}h_linear_interpolation", "fill", filled.sum(), n, sid, "is_filled=True")
        log(run_id, "pm25", f"gap_gt_{FILL_MAX_HOURS}h_left_missing", "flag", v.isna().sum(), n, sid, "not guessed")
        age = (pd.Timestamp.now(tz="UTC") - g.index.max()).total_seconds() / 3600
        if age > 6:
            log(run_id, "pm25", "station_stale_over_6h", "flag", 1, 1, sid, f"latest hour {g.index.max()} is {age:.0f}h old")
        o = pd.DataFrame({"station_id": sid, "pm25_raw": raw, "pm25": v, "is_filled": filled,
                          "is_flagged": bad | stuck | v.isna()}, index=g.index).reset_index()
        o["row_id"] = row_ids(sid, o["ts"])
        out.append(o)
    res = pd.concat(out, ignore_index=True)
    validate(PM_SCHEMA, res, run_id, "pm25")
    return res

def clean_weather(run_id):
    recs = []
    for p in (RAW / "openmeteo").glob("w*.json"):
        d = pd.DataFrame(json.loads(p.read_text())["hourly"])
        d["station_id"], d["fetched"] = int(p.name.split("_")[0][1:]), p.stat().st_mtime
        recs.append(d)
    wx = pd.concat(recs, ignore_index=True)
    wx["ts"] = pd.to_datetime(wx.pop("time"), utc=True)
    wx = wx.sort_values("fetched").drop_duplicates(["station_id", "ts"], keep="last").drop(columns="fetched")
    n = len(wx)
    ints = [v for v in WX_VARS if wx[v].dtype.kind == "i"]
    wx[WX_VARS] = wx[WX_VARS].astype(float)
    if ints:
        log(run_id, "weather", "cast_integer_columns_to_float: " + ",".join(ints), "fix", n, n)

    if wx["temperature_2m"].mean() > 200:
        wx["temperature_2m"] -= 273.15
        log(run_id, "weather", "temperature_kelvin_to_celsius", "fix", n, n)
    for v, (lo, hi) in RANGES.items():
        bad = (wx[v] < lo) | (wx[v] > hi)
        wx[v] = wx[v].mask(bad)
        log(run_id, "weather", f"{v}_outside_{lo}_{hi}", "flag", bad.sum(), n, detail="set to NaN")
        log(run_id, "weather", f"{v}_missing", "flag", wx[v].isna().sum(), n, detail="kept as missing (recent days lag)")
    validate(WX_SCHEMA, wx, run_id, "weather")
    return wx

def clean(run_id):
    CLEANED.mkdir(parents=True, exist_ok=True)
    clean_pm25(run_id).to_parquet(CLEANED / "pm25.parquet", index=False)
    clean_weather(run_id).to_parquet(CLEANED / "weather.parquet", index=False)