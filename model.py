import json, time, tracemalloc
import numpy as np, pandas as pd, lightgbm as lgb
from config import *

WX = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m", "surface_pressure", "precipitation"]
FEATURES = WX + ["pm25_lag24", "pm25_lag48", "pm25_lag168", "pm25_roll24", "hour", "dow", "month", "station_cat"]
GRID = [dict(num_leaves=15, learning_rate=0.05, n_estimators=300, min_child_samples=50),
        dict(num_leaves=31, learning_rate=0.05, n_estimators=300, min_child_samples=50),
        dict(num_leaves=15, learning_rate=0.03, n_estimators=600, min_child_samples=100),
        dict(num_leaves=63, learning_rate=0.03, n_estimators=400, min_child_samples=100)]

def mk(alpha, **p):
    return lgb.LGBMRegressor(objective="quantile", alpha=alpha, random_state=SEED, verbose=-1,
                             deterministic=True, force_row_wise=True, **p)

def main():
    t0 = time.time(); tracemalloc.start()
    df = pd.read_parquet(GOLD / "pm25_gold.parquet")
    df = df[df.pm25.notna() & df.pm25_lag24.notna()].copy()     # same rows for baseline and model
    df["station_cat"] = df["station_id"].astype("category")
    ts = df["ts"].sort_values()
    t1, t2 = ts.iloc[int(len(ts) * 0.70)], ts.iloc[int(len(ts) * 0.85)]
    train, val, test = df[df.ts < t1], df[(df.ts >= t1) & (df.ts < t2)], df[df.ts >= t2].copy()
    print(f"train {len(train)} | val {len(val)} | test {len(test)} | split {t1} / {t2}")

    best = None
    for p in GRID:                                              # tune on validation only
        m = mk(0.5, **p).fit(train[FEATURES], train.pm25)
        mae = np.abs(m.predict(val[FEATURES]) - val.pm25).mean()
        print(p, "val MAE", round(mae, 3))
        if best is None or mae < best[0]: best = (mae, p)
    p = best[1]
    mid, lo, hi = (mk(a, **p).fit(train[FEATURES], train.pm25) for a in (0.5, 0.1, 0.9))

    Xt = test[FEATURES]                                         # test touched here, once
    l, h = lo.predict(Xt), hi.predict(Xt)
    test["pred"] = np.maximum(mid.predict(Xt), 0)
    test["lo"], test["hi"] = np.maximum(np.minimum(l, h), 0), np.maximum(l, h)
    test["base"] = test["pm25_lag24"]
    test["err_m"], test["err_b"] = (test.pred - test.pm25).abs(), (test.base - test.pm25).abs()
    test["covered"] = (test.pm25 >= test.lo) & (test.pm25 <= test.hi)

    rows = []
    for gt, col in (("station", "name"), ("season", "season")):
        for k, g in test.groupby(col):
            rows.append(dict(group_type=gt, group=k, n=len(g), baseline_mae=g.err_b.mean(),
                             model_mae=g.err_m.mean(), coverage_10_90=g.covered.mean()))
    pd.DataFrame(rows).round(3).to_csv(DATA / "errors_by_group.csv", index=False)
    test[["row_id", "station_id", "ts", "pm25", "pred", "lo", "hi", "base"]].to_parquet(DATA / "test_predictions.parquet", index=False)

    secs, peak = time.time() - t0, tracemalloc.get_traced_memory()[1] / 1e6
    m = dict(baseline="same hour yesterday (pm25_lag24)", metric="MAE ug/m3",
             baseline_mae=round(test.err_b.mean(), 3), model_mae=round(test.err_m.mean(), 3),
             improvement_pct=round(100 * (1 - test.err_m.mean() / test.err_b.mean()), 1),
             interval="10th-90th percentile quantile models", interval_coverage=round(test.covered.mean(), 3),
             n_train=len(train), n_val=len(val), n_test=len(test), test_starts=str(t2), params=p,
             seed=SEED, seconds=round(secs, 1), peak_python_mem_mb=round(peak, 1))
    (DATA / "metrics.json").write_text(json.dumps(m, indent=1))
    log = ROOT / "docs" / "optimization_log.md"; log.parent.mkdir(exist_ok=True)
    if not log.exists():
        log.write_text("| date | change | test MAE | seconds | peak MB |\n|---|---|---|---|---|\n")
    with open(log, "a") as f:
        f.write(f"| {pd.Timestamp.now():%Y-%m-%d %H:%M} | TODO describe change | {m['model_mae']} | {m['seconds']} | {m['peak_python_mem_mb']} |\n")
    print(json.dumps(m, indent=1))

if __name__ == "__main__":
    main()