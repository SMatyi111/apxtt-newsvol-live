"""Small fetcher for Dukascopy's public historical price files (datafeed.dukascopy.com).

Two file kinds are used, both BID side:
  day candles : <PAIR>/<YYYY>/<MM0>/<DD>/BID_candles_min_1.bi5   1440 one-minute candles of one UTC day
                record = >i4 seconds-from-day-start, >i4 open, >i4 close, >i4 low, >i4 high, >f4 volume
  hour ticks  : <PAIR>/<YYYY>/<MM0>/<DD>/<HH>h_ticks.bi5       every tick of one UTC hour
                record = >i4 ms-from-hour-start, >i4 ask, >i4 bid, >f4 ask volume, >f4 bid volume
MM0 is the month counted from 0 (January = 00). Prices are integers in points: 1e-3 for JPY pairs, 1e-5 otherwise.
Files are LZMA ("alone" format; tick files may lack the end marker, so a stream decompressor is used).
A day's candle file appears shortly after the UTC day ends; an hour's tick file shortly after the hour ends.
Minutes without any tick (volume 0, flat candle) are dropped, so bars match a broker's M1 series (no bar = no tick).

Raw files are cached on disk (never committed: Dukascopy's data licence). 404 = not published yet (or no data):
it is not cached for today/yesterday so a later run can retry, and cached as empty for older days.
"""
import datetime as dt
import lzma
import os
import time
import urllib.error
import urllib.request

import numpy as np

HOSTS = ("https://datafeed.dukascopy.com/datafeed", "http://datafeed.dukascopy.com/datafeed")
UA = "apxtt-newsvol-live/1.0 (+https://github.com/SMatyi111/apxtt-newsvol-live)"
CANDLE = np.dtype([("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])
TICK = np.dtype([("ms", ">i4"), ("ask", ">i4"), ("bid", ">i4"), ("av", ">f4"), ("bv", ">f4")])


def point(pair):
    return 1e-3 if pair.endswith("JPY") else 1e-5


class NotPublished(Exception):
    pass


class Fetcher:
    """Polite sequential HTTP client with an on-disk cache. `min_gap` seconds between requests; on HTTP 429 it backs
    off (30, 60, 120, 240 s) and retries. `budget` caps the number of network requests per process (None = no cap)."""

    def __init__(self, cache_dir, min_gap=0.5, budget=None, log=print, hard_end_utc=None,
                 waits=(5, 15, 30, 60, 120, 120, 120), timeout=40):
        self.waits = list(waits)
        self.timeout = timeout
        self.cache = cache_dir
        self.min_gap = min_gap
        self.budget = budget
        self.log = log
        self.n_requests = 0
        self.n_429 = 0
        self._last = 0.0
        self._host = 0
        self.hard_end = hard_end_utc  # datetime (UTC, naive) - nothing at or after it may be requested
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------ network
    def _get(self, rel):
        if self.budget is not None and self.n_requests >= self.budget:
            raise RuntimeError("request budget exhausted")
        waits = self.waits
        last_err = None
        for attempt in range(len(waits) + 1):
            gap = time.time() - self._last
            if gap < self.min_gap:
                time.sleep(self.min_gap - gap)
            url = f"{HOSTS[self._host]}/{rel}"
            self._last = time.time()
            self.n_requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotPublished(rel)
                if e.code == 429 or e.code >= 500:
                    if e.code == 429:
                        self.n_429 += 1
                    last_err = e
                    if attempt < len(waits):
                        self.log(f"  HTTP {e.code} on {rel}; waiting {waits[attempt]} s")
                        time.sleep(waits[attempt])
                        continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last_err = e
                self._host = 1 - self._host  # try the other scheme (some networks block one of them)
                if attempt < len(waits):
                    time.sleep(min(waits[attempt], 30))
                    continue
                raise
        raise RuntimeError(f"giving up on {rel}: {last_err!r}")

    def _cached(self, rel, cache_empty):
        path = os.path.join(self.cache, rel.replace("/", "_"))
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        try:
            raw = self._get(rel)
        except NotPublished:
            if cache_empty:
                open(path, "wb").close()
            raise
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, path)
        return raw

    def _check_end(self, start_utc):
        if self.hard_end is not None and start_utc >= self.hard_end:
            raise AssertionError(f"request at/after hard end {self.hard_end}: {start_utc}")

    # ------------------------------------------------------------------ files
    def day_candles(self, pair, day, now_utc=None):
        """M1 BID candles of one UTC day -> structured array (t = epoch s, o h l c float prices, v), volume > 0 only.
        Raises NotPublished if the file is not there (yet)."""
        day = dt.date(day.year, day.month, day.day)
        self._check_end(dt.datetime(day.year, day.month, day.day))
        rel = f"{pair}/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/BID_candles_min_1.bi5"
        now_utc = now_utc or dt.datetime.utcnow()
        old = (now_utc.date() - day).days >= 3
        raw = self._cached(rel, cache_empty=old)
        return decode_candles(raw, pair, day)

    def hour_ticks_m1(self, pair, hour_start):
        """One UTC hour of BID ticks aggregated to M1 bars (same layout as day_candles). NotPublished if missing."""
        self._check_end(hour_start)
        h = hour_start
        rel = f"{pair}/{h.year:04d}/{h.month - 1:02d}/{h.day:02d}/{h.hour:02d}h_ticks.bi5"
        raw = self._cached(rel, cache_empty=False)
        return ticks_to_m1(raw, pair, h)


def _decompress(raw):
    if not raw:
        return b""
    return lzma.LZMADecompressor().decompress(raw)


def decode_candles(raw, pair, day):
    b = _decompress(raw)
    a = np.frombuffer(b[: len(b) // CANDLE.itemsize * CANDLE.itemsize], dtype=CANDLE)
    a = a[a["v"] > 0]
    base = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    pt = point(pair)
    out = np.empty(len(a), dtype=[("t", "i8"), ("o", "f8"), ("h", "f8"), ("l", "f8"), ("c", "f8"), ("v", "f8")])
    out["t"] = base + a["t"].astype(np.int64)
    out["o"] = a["o"] * pt
    out["h"] = a["h"] * pt
    out["l"] = a["l"] * pt
    out["c"] = a["c"] * pt
    out["v"] = a["v"]
    return out


def ticks_to_m1(raw, pair, hour_start):
    b = _decompress(raw)
    a = np.frombuffer(b[: len(b) // TICK.itemsize * TICK.itemsize], dtype=TICK)
    out = np.empty(0, dtype=[("t", "i8"), ("o", "f8"), ("h", "f8"), ("l", "f8"), ("c", "f8"), ("v", "f8")])
    if len(a) == 0:
        return out
    base = int(hour_start.replace(tzinfo=dt.timezone.utc).timestamp())
    minute = a["ms"].astype(np.int64) // 60000
    bid = a["bid"].astype(np.int64)
    keys, first = np.unique(minute, return_index=True)
    last = np.r_[first[1:], len(a)] - 1
    out = np.empty(len(keys), dtype=out.dtype)
    pt = point(pair)
    out["t"] = base + keys * 60
    out["o"] = bid[first] * pt
    out["c"] = bid[last] * pt
    out["h"] = np.maximum.reduceat(bid, first) * pt
    out["l"] = np.minimum.reduceat(bid, first) * pt
    out["v"] = np.add.reduceat(a["bv"].astype(np.float64), first)
    return out
