from dotenv import load_dotenv
import os, requests

load_dotenv()
H = {"X-API-Key": os.environ["OPENAQ_KEY"]}
r = requests.get("https://api.openaq.org/v3/locations", headers=H,
                 params={"iso": "PK", "limit": 5}, timeout=60)
print(r.status_code)
print(r.json()["results"][0]["name"])