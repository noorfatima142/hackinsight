import csv, hashlib, json, time
import pandas as pd, requests
from config import *

H = {"X-API-Key": OPENAQ_KEY}
MAN_COLS = ["source", "query", "fetched_at_utc", "sha256", "rows", "path", "licence"]
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,surface_pressure,precipitation"

def iso(t): return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def get_json(url, params, headers=None, tries=6):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
        except requests.RequestException as e:
            print("network error:", e); time.sleep(5 * (i + 1)); continue
        if r.status_code == 200:
            return r.json()
        print(url, r.status_code, r.text[:150])
        time.sleep(30 if r.status_code == 429 else 3 * (i + 1))
    raise RuntimeError(f"request failed: {url}")

def log_manifest(source, query, path, rows, licence):
    DATA.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(MAN_COLS)
        w.writerow([source, query, iso(pd.Timestamp.now(tz="UTC")), sha256_file(path), rows,
                    path.relative_to(ROOT).as_posix(), licence])

def save_raw(source, key, payload, nrows, query, licence):
    d = RAW / source; d.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, sort_keys=True).encode()
    sha = hashlib.sha256(blob).hexdigest()
    p = d / f"{key}_{sha[:12]}.json"
    if p.exists(): return          # identical content already stored
    p.write_bytes(blob)
    log_manifest(source, query, p, nrows, licence)

def stations_cached():
    f = DATA / "stations.csv"
    if f.exists(): return pd.read_csv(f)
    out, page = [], 1
    while True:
        res = get_json("https://api.openaq.org/v3/locations",
                       {"iso": "PK", "limit": 100, "page": page}, H)["results"]
        if not res: break
        out += res; page += 1; time.sleep(1)
    rows = []
    for L in out:
        s = next((x["id"] for x in L["sensors"] if x["parameter"]["name"] == "pm25"), None)
        a = (L.get("datetimeFirst") or {}).get("utc"); b = (L.get("datetimeLast") or {}).get("utc")
        if s is None or not a or not b: continue
        rows.append(dict(station_id=L["id"], sensor_id=s, name=L["name"], city=L.get("locality") or L["name"],
                         provider=(L.get("provider") or {}).get("name"),
                         lat=L["coordinates"]["latitude"], lon=L["coordinates"]["longitude"],
                         first=pd.Timestamp(a), last=pd.Timestamp(b)))
    df = pd.DataFrame(rows)
    df["days"] = (df["last"] - df["first"]).dt.days
    df["stale"] = (pd.Timestamp.now(tz="UTC") - df["last"]).dt.days
    ok = df[(df.days >= MIN_STATION_DAYS) & (df.stale <= MAX_STALE_DAYS)].sort_values("days", ascending=False)
    chosen = []
    for _, r in ok.iterrows():          # spread: skip stations next to one already chosen
        if all(abs(r.lat - c.lat) + abs(r.lon - c.lon) > 0.1 for c in chosen):
            chosen.append(r)
        if len(chosen) == N_STATIONS: break
    if not chosen: raise RuntimeError("No station passed the history/staleness filter; send me stations_pm25.csv")
    sel = pd.DataFrame(chosen)
    sel["first"], sel["last"] = sel["first"].astype(str), sel["last"].astype(str)
    DATA.mkdir(parents=True, exist_ok=True)
    sel.to_csv(f, index=False)
    print("selected stations:\n", sel[["station_id", "name", "city", "days"]].to_string())
    return sel

def fetch_openaq(sensor_id, start, end):
    rows, page = [], 1
    while True:
        res = get_json(f"https://api.openaq.org/v3/sensors/{sensor_id}/hours",
                       {"datetime_from": iso(start), "datetime_to": iso(end), "limit": 1000, "page": page}, H)["results"]
        rows += res
        if len(res) < 1000: break
        page += 1; time.sleep(1.1)
    return rows

def fetch_weather(st, start, end):
    p = {"latitude": st.lat, "longitude": st.lon, "start_date": start.strftime("%Y-%m-%d"),
         "hourly": HOURLY, "timezone": "UTC"}
    for e in (end, end - pd.Timedelta(days=7)):
        try:
            return get_json("https://archive-api.open-meteo.com/v1/archive",
                            {**p, "end_date": e.strftime("%Y-%m-%d")}, tries=2)
        except RuntimeError:
            continue
    raise RuntimeError("weather fetch failed")

def run_ingest():
    stations = stations_cached()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"sensors": {}, "last_fetch": {}}
    end = pd.Timestamp.now(tz="UTC").floor("h")
    for st in stations.itertuples():
        key = str(st.station_id)
        start = (pd.Timestamp(state["sensors"][key]) - pd.Timedelta(hours=6)) if key in state["sensors"] \
            else end - pd.Timedelta(days=HISTORY_DAYS)
        rows = fetch_openaq(st.sensor_id, start, end)
        print(f"station {key} ({st.name}): {len(rows)} hourly rows")
        if rows:
            if not (rows[0].get("period") or {}).get("datetimeFrom"):
                print("WARNING unexpected OpenAQ format, keys:", list(rows[0].keys()))
            save_raw("openaq", f"s{key}", rows, len(rows),
                     f"sensors/{st.sensor_id}/hours {iso(start)}..{iso(end)}",
                     f"OpenAQ via provider {st.provider}; provider licence applies (verify)")
            ends = [r["period"]["datetimeTo"]["utc"] for r in rows
                    if (r.get("period") or {}).get("datetimeTo")]
            state["sensors"][key] = max(ends) if ends else iso(end)
        wx = fetch_weather(st, start, end)
        save_raw("openmeteo", f"w{key}", wx, len(wx["hourly"]["time"]),
                 f"archive lat={st.lat} lon={st.lon} from {start.date()}", "CC BY 4.0 (Open-Meteo)")
        STATE.write_text(json.dumps(state))
    now = iso(pd.Timestamp.now(tz="UTC"))
    state["last_fetch"] = {"openaq": now, "openmeteo": now}
    STATE.write_text(json.dumps(state))

def verify_raw():
    m = pd.read_csv(MANIFEST); bad = 0
    for r in m.itertuples():
        p = ROOT / r.path
        if not p.exists() or sha256_file(p) != r.sha256:
            print("HASH MISMATCH:", r.path); bad += 1
    print(f"manifest verified: {len(m)} raw files, {bad} problems")
    if bad: raise RuntimeError("raw file hash mismatch")