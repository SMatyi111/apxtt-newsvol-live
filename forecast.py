"""Forecast the next UTC hour's high-low range for the 7 majors and append it to log/forecasts.jsonl.

Called hourly by .github/workflows/hourly.yml (cron minute 35). Target = the next full UTC hour after `now`.
- Before 2026-10-19 00:00 UTC (log start) nothing is fetched or written (warm-up), except with --selftest.
- Store-clock Saturday/Sunday (FX closed) -> nothing written.
- A target already in the log is never forecast twice (idempotent).
--selftest: replay the whole pipeline at a fixed, already-seen time (default 2026-10-07 13:35 UTC, before the
  sealed window) and append the result to log/warmup.jsonl marked "warmup / not scored". Proves the runner can
  reach Dukascopy and that the code runs; it is never part of the score.
Prints TARGET=<iso> on success so the workflow can write the push receipt.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsvol.features import utc_to_store  # noqa: E402
from newsvol.live import (FORECASTS, LOG_START, SEALED, WARMUP, append_chained, frozen_hashes, iso, make_forecasts,  # noqa: E402
                          new_fetcher, read_jsonl, utcnow)

ap = argparse.ArgumentParser()
ap.add_argument("--selftest", action="store_true")
ap.add_argument("--asof", default="2026-10-07T13:35")
a = ap.parse_args()

now = utcnow()
if a.selftest:
    asof = dt.datetime.fromisoformat(a.asof)
    assert asof + dt.timedelta(hours=1) <= SEALED[0], "self-test must use already-seen data only"
    target = asof.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    f = new_fetcher()
    res = make_forecasts(f, target, asof)
    rec = {"mode": "warmup-selftest", "scored": False, "note": "replay on already-seen data; never scored",
           "run_utc": iso(now), "asof_utc": iso(asof), "target_hour_utc": iso(target), **frozen_hashes(),
           "requests": f.n_requests, "http_429": f.n_429, **res}
    append_chained(WARMUP, rec)
    ok = sum(1 for v in res["pairs"].values() if v.get("status") == "ok")
    print(f"selftest target {iso(target)}: {ok}/7 pairs forecast, {f.n_requests} requests")
    sys.exit(0)

target = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
if target < LOG_START:
    if LOG_START - target <= dt.timedelta(hours=3):
        # pre-warm the runner's private raw-data cache with the lookback inputs of the first scored hour.
        # Inputs only (registry rule D1: lookback inputs may cross a sealed window); nothing is computed for,
        # written about, or printed from any hour before the log start.
        f = new_fetcher()
        make_forecasts(f, LOG_START, now)
        print(f"pre-warm: cached lookback inputs for the first scored hour ({f.n_requests} requests); nothing written")
        sys.exit(0)
    print(f"warm-up: target {iso(target)} is before the log start {iso(LOG_START)}; nothing fetched or written")
    sys.exit(0)
if utc_to_store(target).weekday() >= 5:
    print(f"market closed at {iso(target)} (store clock weekend); nothing written")
    sys.exit(0)
if any(r["target_hour_utc"] == iso(target) for r in read_jsonl(FORECASTS)):
    print(f"forecast for {iso(target)} already logged")
    sys.exit(0)
f = new_fetcher()
res = make_forecasts(f, target, now)
done = utcnow()
if done >= target:
    print(f"computation finished after the hour started ({iso(done)}); still logged, will be marked late")
rec = {"mode": "live", "target_hour_utc": iso(target), "created_utc": iso(done), "run_started_utc": iso(now),
       **frozen_hashes(), "requests": f.n_requests, "github_run_id": os.environ.get("GITHUB_RUN_ID"),
       "code_commit": os.environ.get("GITHUB_SHA"), **res}
append_chained(FORECASTS, rec)
print(f"TARGET={iso(target)}")
