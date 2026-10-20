# %%
from dotenv import load_dotenv
import os, requests, pandas as pd
load_dotenv()
H = {"X-API-Key": os.environ["OPENAQ_KEY"]}

# %%
r = requests.get("https://api.openaq.org/v3/locations", headers=H,
                 params={"iso": "PK", "limit": 1000}, timeout=60)
r.raise_for_status()
results = r.json()["results"]
print(len(results), "locations in Pakistan")

# %%
rows = []
for L in results:
    pm25 = next((s["id"] for s in L["sensors"] if s["parameter"]["name"] == "pm25"), None)
    if pm25 is None:
        continue
    rows.append(dict(
        loc_id=L["id"], name=L["name"],
        provider=(L.get("provider") or {}).get("name"),
        lat=L["coordinates"]["latitude"], lon=L["coordinates"]["longitude"],
        first=(L.get("datetimeFirst") or {}).get("utc"),
        last=(L.get("datetimeLast") or {}).get("utc"),
        pm25_sensor=pm25))
df = pd.DataFrame(rows)
df["first"] = pd.to_datetime(df["first"])
df["last"] = pd.to_datetime(df["last"])
df["days"] = (df["last"] - df["first"]).dt.days
df = df.sort_values("days", ascending=False)
# %%
# %%
print("missing first/last:", df["first"].isna().sum(), df["last"].isna().sum())
print(df["days"].describe())
print(df["stale_days"].describe())
print("days >= 365:", (df["days"] >= 365).sum())
print("stale <= 30:", (df["stale_days"] <= 30).sum())
print("both:", ((df["days"] >= 365) & (df["stale_days"] <= 30)).sum())
print(df.sort_values("days", ascending=False).head(15).to_string())
df.to_csv("stations_pm25.csv", index=False)