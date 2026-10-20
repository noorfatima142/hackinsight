import json, shutil, sys, time, uuid
import pandas as pd
from config import *
import ingest, clean, gold

def write_status(run_id, ok, seconds, err=""):
    prev = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        lf = json.loads(STATE.read_text()).get("last_fetch", {})
        pm = pd.read_parquet(CLEANED / "pm25.parquet", columns=["ts", "pm25"])
        wx = pd.read_parquet(CLEANED / "weather.parquet", columns=["ts", "temperature_2m"])
        src = {"openaq": {"last_fetch_utc": lf.get("openaq"), "latest_data_utc": str(pm.loc[pm.pm25.notna(), "ts"].max())},
               "openmeteo": {"last_fetch_utc": lf.get("openmeteo"), "latest_data_utc": str(wx.loc[wx.temperature_2m.notna(), "ts"].max())}}
    except Exception:
        src = prev.get("sources", {})
    STATUS.write_text(json.dumps({"run_id": run_id, "last_run_utc": now,
        "last_run_status": "success" if ok else "failed", "error": err, "seconds": round(seconds, 1),
        "last_success_utc": now if ok else prev.get("last_success_utc"), "sources": src}, indent=1))

def run(fresh=False):
    if fresh and DATA.exists():
        shutil.rmtree(DATA)
    DATA.mkdir(parents=True, exist_ok=True)
    run_id, t0 = uuid.uuid4().hex[:8], time.time()
    try:
        ingest.run_ingest(); ingest.verify_raw(); clean.clean(run_id); gold.build_gold(run_id)
    except Exception as e:
        write_status(run_id, False, time.time() - t0, repr(e)[:300]); raise
    write_status(run_id, True, time.time() - t0)
    q = pd.read_csv(QUALITY_LOG)
    print(f"\nrun {run_id} done in {time.time() - t0:.0f}s. Quality decisions this run:")
    print(q[q.run_id == run_id].groupby("action")["rows_affected"].agg(["count", "sum"]))

if __name__ == "__main__":
    run(fresh="--fresh" in sys.argv)