"""Pre-push guard for the live log (AMENDMENTS.md A1). Exit 0 = safe to push, non-zero = do not push.

Checks, for every file under log/ plus scoreboard.json:
- no git conflict markers, every log line is a valid JSON object, every file ends with a newline;
- forecasts.jsonl and realized.jsonl hash chains are intact, and no target hour appears twice in either;
- append-only: the version on origin/main (if it exists there) is a byte prefix of the local file, so no past
  line was dropped, edited or reordered.
Run from the repo root: python ops/check_logs.py [--base origin/main]
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from newsvol.live import FORECASTS, REALIZED, LogCorrupt, read_jsonl, verify_chain  # noqa: E402

MARKERS = (b"<<<<<<< ", b"=======\n", b">>>>>>> ", b"|||||||")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    a = ap.parse_args()
    errors = []
    logdir = os.path.join(ROOT, "log")
    files = sorted(os.path.join(logdir, f) for f in os.listdir(logdir) if f.endswith(".jsonl"))
    sb = os.path.join(ROOT, "scoreboard.json")
    for path in files + ([sb] if os.path.exists(sb) else []):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        data = open(path, "rb").read()
        for line in data.splitlines(keepends=True):
            if line.startswith(MARKERS) or line.rstrip(b"\r\n") in (b"=======", b"<<<<<<<", b">>>>>>>"):
                errors.append(f"{rel}: conflict marker {line[:40]!r}")
                break
        if data and not data.endswith(b"\n"):
            errors.append(f"{rel}: does not end with a newline")
        try:
            if path.endswith(".jsonl"):
                read_jsonl(path)
            else:
                json.loads(data.decode("utf-8"))
        except (LogCorrupt, ValueError) as e:
            errors.append(f"{rel}: {e}")
            continue
        if path.endswith(".jsonl"):
            base = subprocess.run(["git", "show", f"{a.base}:{rel}"], cwd=ROOT, capture_output=True)
            if base.returncode == 0 and not data.startswith(base.stdout):
                errors.append(f"{rel}: {a.base} version is not a prefix of the local file (past lines changed)")
    for path in (FORECASTS, REALIZED):
        try:
            ok, bad = verify_chain(path)
            if not ok:
                errors.append(f"{os.path.basename(path)}: hash chain broken at record {bad}")
            hours = [r.get("target_hour_utc") for r in read_jsonl(path)]
            dup = sorted({h for h in hours if hours.count(h) > 1})
            if dup:
                errors.append(f"{os.path.basename(path)}: target hours logged twice: {dup}")
        except LogCorrupt:
            pass  # already reported above
    if errors:
        print("LOG CHECK FAILED, do not push:\n  " + "\n  ".join(errors), file=sys.stderr)
        sys.exit(1)
    print("log check ok")


if __name__ == "__main__":
    main()
