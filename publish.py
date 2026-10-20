import os
from huggingface_hub import HfApi, CommitOperationAdd
from config import *

DATA_FILES = [MANIFEST, QUALITY_LOG, STATUS, DATA / "metrics.json", DATA / "errors_by_group.csv",
              DATA / "stations.csv", GOLD / "pm25_gold.parquet"]
REQS = b"gradio\npandas\npyarrow\nscikit-learn\npython-dotenv\n"

def push(code=False):
    token, repo = os.environ.get("HF_TOKEN"), os.environ.get("HF_SPACE")
    if not token or not repo:
        print("HF_TOKEN / HF_SPACE not set, skipping publish"); return
    files = [ROOT / "app.py", ROOT / "rag.py", ROOT / "config.py", *TRUSTED_DOCS.glob("*.txt")] if code else DATA_FILES
    ops = [CommitOperationAdd(path_in_repo=p.relative_to(ROOT).as_posix(), path_or_fileobj=str(p)) for p in files if p.exists()]
    if code: ops.append(CommitOperationAdd(path_in_repo="requirements.txt", path_or_fileobj=REQS))
    HfApi(token=token).create_commit(repo_id=repo, repo_type="space", operations=ops, commit_message="refresh")

if __name__ == "__main__":
    import sys
    push(code="--code" in sys.argv)