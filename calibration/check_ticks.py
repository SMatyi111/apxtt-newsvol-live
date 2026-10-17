"""Check that M1 bars built from Dukascopy hourly BID tick files equal the BID M1 day-candle file (seen day only).
Run: python calibration/check_ticks.py <cache> <PAIR> <YYYY-MM-DD> <hour> [<hour> ...]"""
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from newsvol.dukascopy import Fetcher  # noqa: E402

cache, pair, day = sys.argv[1], sys.argv[2], dt.date.fromisoformat(sys.argv[3])
assert day < dt.date(2026, 10, 10)
f = Fetcher(cache, min_gap=0.5, hard_end_utc=dt.datetime(2026, 10, 10))
c = f.day_candles(pair, day)
for h in map(int, sys.argv[4:]):
    t0 = dt.datetime(day.year, day.month, day.day, h)
    m = f.hour_ticks_m1(pair, t0)
    base = int(t0.replace(tzinfo=dt.timezone.utc).timestamp())
    cc = c[(c["t"] >= base) & (c["t"] < base + 3600)]
    same_t = np.array_equal(m["t"], cc["t"])
    eq = {k: bool(same_t and np.allclose(m[k], cc[k], rtol=0, atol=1e-9)) for k in ("o", "h", "l", "c")}
    print(pair, t0, "minutes ticks/candles", len(m), len(cc), "same minutes", same_t, eq,
          "hour range ticks/candles", round(m["h"].max() - m["l"].min(), 6), round(cc["h"].max() - cc["l"].min(), 6))
