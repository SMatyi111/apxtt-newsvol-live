"""Download Dukascopy BID M1 day files for the calibration window and reduce them to hourly inputs per pair.

HARD END: nothing on or after 2026-10-10 00:00 UTC is requested (asserted in the fetcher). 2026-10-10..10-18 is a
sealed one-shot confirmation window; the live log starts 2026-10-19.

Output per pair (derived data only, raw files stay in the cache and are never committed):
  <out>/<PAIR>_vol.csv   valid store hours: rv_bp lrv lc jflag lj n
  <out>/<PAIR>_ohlc.csv  store hours Mon-Fri with any bar: o h l c nmin
Run: python calibration/fetch_history.py --cache <dir> --out <dir> [--pairs EURUSD,...] [--start 2018-04-29]
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from newsvol.dukascopy import Fetcher, NotPublished  # noqa: E402
from newsvol.features import G8, hourly_from_m1  # noqa: E402

HARD_END = dt.datetime(2026, 10, 10)

ap = argparse.ArgumentParser()
ap.add_argument("--cache", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--pairs", default=",".join(G8))
ap.add_argument("--start", default="2018-04-29")
ap.add_argument("--end", default="2026-10-09")  # inclusive UTC day
ap.add_argument("--gap", type=float, default=0.3)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
end = dt.date.fromisoformat(a.end)
assert dt.datetime(end.year, end.month, end.day) + dt.timedelta(days=1) <= HARD_END
f = Fetcher(a.cache, min_gap=a.gap, hard_end_utc=HARD_END)
days = [d.date() for d in pd.date_range(a.start, a.end) if d.dayofweek != 5]  # no FX on a UTC Saturday
for p in a.pairs.split(","):
    if os.path.exists(f"{a.out}/{p}_vol.csv"):
        print(p, "exists", flush=True)
        continue
    parts, missing = [], 0
    for d in days:
        try:
            parts.append(f.day_candles(p, d))
        except NotPublished:
            missing += 1
    m1 = np.concatenate(parts)
    m1 = m1[np.argsort(m1["t"], kind="stable")]
    assert m1["t"].max() < HARD_END.replace(tzinfo=dt.timezone.utc).timestamp()
    vol, ohlc = hourly_from_m1(m1)
    vol.index.name = ohlc.index.name = "obs"
    vol.to_csv(f"{a.out}/{p}_vol.csv", date_format="%Y-%m-%d %H:%M")
    ohlc.to_csv(f"{a.out}/{p}_ohlc.csv", date_format="%Y-%m-%d %H:%M")
    print(p, len(m1), "bars", len(vol), "valid hours", "missing days", missing, "requests", f.n_requests, "429s", f.n_429, flush=True)
