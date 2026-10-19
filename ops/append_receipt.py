"""Append one push receipt to log/receipts.jsonl (AMENDMENTS.md A1). Idempotent: a receipt with the same target hour
and run id is never written twice, so ops/commit_push.sh can re-run it after a reset to origin/main.
The pushed time is the runner clock read right after the forecast push returned (passed in, never re-read here).
Usage: python ops/append_receipt.py <target_hour_utc> <commit> <pushed_utc> <run_id>
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from newsvol.live import RECEIPTS, read_jsonl  # noqa: E402

target, commit, pushed, run_id = sys.argv[1:5]
if any(r.get("target_hour_utc") == target and str(r.get("run_id")) == run_id for r in read_jsonl(RECEIPTS)):
    print(f"receipt for {target} run {run_id} already logged")
    sys.exit(0)
if os.path.exists(RECEIPTS) and os.path.getsize(RECEIPTS):
    with open(RECEIPTS, "rb") as fh:
        fh.seek(-1, os.SEEK_END)
        if fh.read(1) != b"\n":
            sys.exit(f"{RECEIPTS}: last line has no newline; refusing to append")
rec = {"target_hour_utc": target, "commit": commit, "pushed_utc": pushed, "run_id": run_id,
       "note": "runner UTC clock read after the push returned"}
with open(RECEIPTS, "a", encoding="utf-8", newline="\n") as fh:
    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
print(f"receipt appended for {target}")
