"""Model inputs from one-minute BID bars: the hourly realised-vol frame, HAR-CJ state, market factor, ATR, same-hour mean.

Everything is computed on the **store clock** of the original research: New York wall time + 7 h. It is a whole-hour
shift of UTC (UTC+2 while New York is on standard time, UTC+3 on daylight time), so every store hour is exactly one
UTC hour. Store 00:00 = New York 17:00 (the FX day roll). The store clock only labels hours (hour-of-day, weekday and
month dummies, the Monday-Friday filter); all records in the public log are written in UTC.

Per store hour with >= 50 clean M1 returns (returns across a gap > 1 minute dropped) and rv > 0, Monday-Friday:
  rv  = sum r^2 ; bv = (pi/2) n/nb sum |r_i||r_i-1| ; tq = n mu43^-3 n/nt sum |r_i r_i-1 r_i-2|^(4/3)
  Huang-Tauchen ratio z, jump if z > 3.09 (99.9%) ; j = rv - bv if jump else 0 ; c = rv - j
  lrv = 0.5 ln(rv 1e8) ; lc = 0.5 ln(c 1e8) ; jflag ; lj = 0.5 ln(1 + j 1e8)      (1e8: bp^2 units)
This is fx-vol-seasonality-2026/scripts/build_hourly_m1.py, vectorised; HAR-CJ means and the factor follow
product_check/scripts/compare.py (row-based windows over valid hours, factor = mean lrv of the other G8 pairs
present in the same hour).
"""
import datetime as dt
import math

import numpy as np
import pandas as pd

MU43 = 2 ** (2 / 3) * math.gamma(7 / 6) / math.gamma(0.5)
THETA = (math.pi / 2) ** 2 + math.pi - 5
YEARS_ORIGIN = pd.Timestamp("2018-06-01")  # store clock, as in the research ("years" counter)
G8 = ("AUDCAD AUDCHF AUDJPY AUDNZD AUDUSD CADCHF CADJPY CHFJPY EURAUD EURCAD EURCHF EURGBP EURJPY EURNZD EURUSD "
      "GBPAUD GBPCAD GBPCHF GBPJPY GBPNZD GBPUSD NZDCAD NZDCHF NZDJPY NZDUSD USDCAD USDCHF USDJPY").split()
MAJORS = "EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD".split()


def pip_size(p):
    return 0.01 if p.endswith("JPY") else 0.0001


# ---------------------------------------------------------------------------------------------------- clock
def _us_dst_bounds(year):
    mar1 = dt.datetime(year, 3, 1)
    start = mar1 + dt.timedelta(days=(6 - mar1.weekday()) % 7 + 7, hours=7)   # 2nd Sunday of March, 02:00 EST
    nov1 = dt.datetime(year, 11, 1)
    end = nov1 + dt.timedelta(days=(6 - nov1.weekday()) % 7, hours=6)          # 1st Sunday of November, 02:00 EDT
    return start, end


def store_offset_hours(utc):
    """Hours to add to a naive UTC datetime to get the store clock (NY + 7 h): 3 during US DST, else 2."""
    s, e = _us_dst_bounds(utc.year)
    return 3 if s <= utc < e else 2


def utc_to_store(utc):
    return utc + dt.timedelta(hours=store_offset_hours(utc))


def store_to_utc(store):
    # store hours are never ambiguous for FX (the US switch happens on a Sunday 02:00 NY while FX is closed)
    u = store - dt.timedelta(hours=2)
    return store - dt.timedelta(hours=store_offset_hours(u - dt.timedelta(hours=1)))


def epoch_utc_to_store(t):
    """Vectorised: int64 UTC epoch seconds -> int64 store-clock epoch seconds (store time relabelled as UTC)."""
    t = np.asarray(t, dtype=np.int64)
    if len(t) == 0:
        return t
    years = range(dt.datetime.utcfromtimestamp(int(t.min())).year, dt.datetime.utcfromtimestamp(int(t.max())).year + 1)
    off = np.full(len(t), 2 * 3600, dtype=np.int64)
    for y in years:
        s, e = _us_dst_bounds(y)
        s = int(s.replace(tzinfo=dt.timezone.utc).timestamp())
        e = int(e.replace(tzinfo=dt.timezone.utc).timestamp())
        off[(t >= s) & (t < e)] = 3 * 3600
    return t + off


# ---------------------------------------------------------------------------------------------------- per hour
def hourly_from_m1(m1):
    """m1: structured array/DataFrame with t (UTC epoch s, ascending, unique), o h l c. Returns
    (vol, ohlc): vol = valid store hours with lrv lc jflag lj rv_bp n ; ohlc = every store hour Mon-Fri with any bar:
    o h l c nmin. Both indexed by store hour (naive Timestamp)."""
    t_utc = np.asarray(m1["t"], dtype=np.int64)
    if len(t_utc) == 0:
        e = pd.DataFrame()
        return e, e
    t = epoch_utc_to_store(t_utc)
    c = np.asarray(m1["c"], dtype=float)
    hk = t - t % 3600
    r = np.full(len(t), np.nan)
    ok = np.zeros(len(t), bool)
    ok[1:] = (t_utc[1:] - t_utc[:-1]) == 60
    lnc = np.log(c)
    r[1:] = lnc[1:] - lnc[:-1]
    r[~ok] = np.nan
    a = np.abs(r)
    a1 = np.r_[np.nan, a[:-1]]
    a2 = np.r_[np.nan, np.nan, a[:-2]]
    same1 = np.r_[False, hk[1:] == hk[:-1]]
    same2 = np.r_[False, False, hk[2:] == hk[:-2]]
    bvp = np.where(same1, a * a1, np.nan)
    tqp = np.where(same2, (a * a1 * a2) ** (4 / 3), np.nan)
    df = pd.DataFrame({"hk": hk, "r2": r * r, "rn": np.isfinite(r).astype(int), "bvp": bvp, "bn": np.isfinite(bvp).astype(int),
                       "tqp": tqp, "tn": np.isfinite(tqp).astype(int)})
    g = df.groupby("hk")
    h = pd.DataFrame({"n": g["rn"].sum(), "rv": g["r2"].sum(), "bvs": g["bvp"].sum(), "nb": g["bn"].sum(),
                      "tqs": g["tqp"].sum(), "nt": g["tn"].sum()})
    h = h[(h["n"] >= 50) & (h["rv"] > 0)]
    n = h["n"]
    bv = ((np.pi / 2) * h["bvs"] * n / h["nb"]).clip(lower=1e-14)
    tq = n * MU43 ** -3 * h["tqs"] * n / h["nt"]
    z = ((h["rv"] - bv) / h["rv"]) / np.sqrt(THETA / n * np.maximum(1, tq / bv ** 2))
    jump = (z > 3.09) & (h["rv"] > bv)
    j = np.where(jump, h["rv"] - bv, 0.0)
    cc = h["rv"] - j
    vol = pd.DataFrame(index=pd.to_datetime(h.index.values, unit="s"))
    vol["rv_bp"] = np.sqrt(h["rv"].values) * 1e4
    vol["lrv"] = 0.5 * np.log(h["rv"].values * 1e8)
    vol["lc"] = 0.5 * np.log(cc.values * 1e8)
    vol["jflag"] = jump.values.astype(int)
    vol["lj"] = 0.5 * np.log1p(j * 1e8)
    vol["n"] = n.values
    vol = vol[vol.index.dayofweek <= 4]
    po = pd.DataFrame({"hk": hk, "o": np.asarray(m1["o"], float), "h": np.asarray(m1["h"], float),
                       "l": np.asarray(m1["l"], float), "c": c})
    go = po.groupby("hk")
    ohlc = pd.DataFrame({"o": go["o"].first(), "h": go["h"].max(), "l": go["l"].min(), "c": go["c"].last(), "nmin": go["c"].count()})
    ohlc.index = pd.to_datetime(ohlc.index.values, unit="s")
    ohlc = ohlc[ohlc.index.dayofweek <= 4]
    return vol, ohlc


def add_factor(vols):
    """vols: {pair: vol frame}. Adds cf = mean lrv of the OTHER pairs present in the same store hour (in place)."""
    wide = pd.DataFrame({p: v["lrv"] for p, v in vols.items() if len(v)})
    tot, cnt = wide.sum(axis=1, min_count=1), wide.notna().sum(axis=1)
    for p, v in vols.items():
        if len(v):
            v["cf"] = ((tot.loc[v.index] - v["lrv"]) / (cnt.loc[v.index] - 1)).replace([np.inf, -np.inf], np.nan)
    return vols


def state(vol, ohlc):
    """Per valid hour s, the model state 'after hour s' (what a forecast made once hour s is complete may use):
    c1 c24 c120 lj1 jf24 lj24 f1 f24 (+ l1 l24 l120 for the research row filter) ; and per OHLC hour the ATR state.
    Windows are rows of valid hours, exactly as compare.py's shift(1).rolling(k) (shift applied later by as-of)."""
    v = vol
    var, cv = np.exp(2 * v["lrv"]), np.exp(2 * v["lc"])
    s = pd.DataFrame(index=v.index)
    s["c1"] = v["lc"]
    s["c24"] = 0.5 * np.log(cv.rolling(24).mean())
    s["c120"] = 0.5 * np.log(cv.rolling(120).mean())
    s["lj1"] = v["lj"]
    s["jf24"] = v["jflag"].rolling(24).mean()
    s["lj24"] = v["lj"].rolling(24).mean()
    s["f1"] = v["cf"]
    s["f24"] = v["cf"].rolling(24).mean()
    s["l1"] = v["lrv"]
    s["l24"] = 0.5 * np.log(var.rolling(24).mean())
    s["l120"] = 0.5 * np.log(var.rolling(120).mean())
    o = ohlc
    pc = o["c"].shift(1)
    tr = np.maximum(o["h"] - o["l"], np.maximum((o["h"] - pc).abs(), (o["l"] - pc).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    a = pd.DataFrame(index=o.index)
    a["atr_bp"] = atr / o["c"] * 1e4
    a["close"] = o["c"]
    return s, a


def asof(frame, keys):
    """For each key time D (store clock): the last row of `frame` with index + 1 h <= D, i.e. hours complete by D.
    Returns a frame aligned to keys (NaN where nothing qualifies)."""
    keys = pd.DatetimeIndex(keys)
    pos = frame.index.searchsorted(keys - pd.Timedelta(hours=1), side="right") - 1
    out = frame.iloc[np.clip(pos, 0, None)].copy()
    out.index = keys
    out[pos < 0] = np.nan
    out["state_hour"] = np.where(pos >= 0, frame.index.values[np.clip(pos, 0, None)], np.datetime64("NaT"))
    return out


def same_hour_mean(vol, ohlc, target, k=20, min_n=12):
    """Mean range (bp) of the same store hour over the previous k valid rows of that hour before `target`
    (compare.py's m20_range), NaN if fewer than min_n of them have a positive range."""
    rng = (1e4 * np.log(ohlc["h"] / ohlc["l"])).reindex(vol.index)
    rng = rng.where(rng > 0)
    prev = rng[(vol.index < target) & (vol.index.hour == target.hour)].iloc[-k:]
    return float(prev.mean()) if prev.notna().sum() >= min_n else float("nan")
