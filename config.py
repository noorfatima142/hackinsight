import os, pathlib
from dotenv import load_dotenv
load_dotenv()
ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW, CLEANED, GOLD = DATA / "raw", DATA / "cleaned", DATA / "gold"
MANIFEST, QUALITY_LOG = DATA / "manifest.csv", DATA / "quality_log.csv"
STATE, STATUS = DATA / "state.json", DATA / "status.json"
WAREHOUSE = DATA / "warehouse.duckdb"
TRUSTED_DOCS = ROOT / "docs" / "trusted"
OPENAQ_KEY = os.environ.get("OPENAQ_KEY", "")
N_STATIONS, HISTORY_DAYS = 6, 730
MIN_STATION_DAYS, MAX_STALE_DAYS = 365, 30
FILL_MAX_HOURS, SEED = 3, 42