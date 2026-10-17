"""Research-identical hourly frame (product_check compare.py) for calibration and checks."""
import numpy as np
import pandas as pd

from .features import G8, add_factor, asof, pip_size, state
from .model import EVS, TERMS, own_events

START = pd.Timestamp("2018-06-01")


def load_frames(data, hard_end, start_vol=START, start_ohlc=pd.Timestamp("2018-05-01")):
    vols, ohlcs = {}, {}
    for p in G8:
        v = pd.read_csv(f"{data}/{p}_vol.csv", index_col="obs", parse_dates=True)
        o = pd.read_csv(f"{data}/{p}_ohlc.csv", index_col="obs", parse_dates=True)
        assert v.index.max() < hard_end and o.index.max() < hard_end
        vols[p] = v[v.index >= start_vol].copy()
        ohlcs[p] = o[o.index >= start_ohlc]
    add_factor(vols)
    return vols, ohlcs


def frame(p, lag, vols, ohlcs, cal):
    v, o = vols[p], ohlcs[p]
    s, at = state(v, o)
    T = v.index
    D = T - pd.Timedelta(hours=lag - 1)
    x = asof(s, D).drop(columns="state_hour")
    x.index = T
    atx = asof(at, D)
    x["atr_bp"] = atx["atr_bp"].values
    x["data_lag_h"] = ((T - pd.DatetimeIndex(atx["state_hour"])) / pd.Timedelta(hours=1)).values
    rng = 1e4 * np.log(o["h"] / o["l"])
    x["range_bp"] = rng.reindex(T).values
    x["pc"] = o["c"].shift(1).reindex(T).values
    x["pipconv"] = x["pc"] / 1e4 / pip_size(p)
    x["rv_bp"] = v["rv_bp"]
    sr = x["range_bp"].where(x["range_bp"] > 0)
    srv = x["rv_bp"].where(x["rv_bp"] > 0)
    hr = T.hour
    for nm, ser in (("range", sr), ("rv", srv)):
        g = ser.groupby(hr)
        x[f"yday_{nm}"] = g.shift(1)
        x[f"m5_{nm}"] = g.transform(lambda z: z.shift(1).rolling(5, min_periods=3).mean())
        x[f"m20_{nm}"] = g.transform(lambda z: z.shift(1).rolling(20, min_periods=12).mean())
    # previous store day's range (only used in the research row filter)
    dd = o.index.normalize()
    d = pd.DataFrame({"h": o["h"].groupby(dd).max(), "l": o["l"].groupby(dd).min()})
    d = d[d.index.dayofweek <= 4]
    x["prevday_range"] = (1e4 * np.log(d["h"] / d["l"])).shift(1).reindex(T.normalize()).values
    X = pd.DataFrame(index=T)
    X["const"] = 1.0
    for i in range(1, 24):
        X[f"h_{i}"] = (hr == i).astype(float)
    for i in range(2, 6):
        X[f"w_{i}"] = (T.dayofweek + 1 == i).astype(float)
    for i in range(2, 13):
        X[f"m_{i}"] = (T.month == i).astype(float)
    X["years"] = (T - START).total_seconds() / (365.25 * 86400)
    for k in ["c1", "c24", "c120", "lj1", "jf24", "lj24", "f1", "f24"]:
        X[k] = x[k]
    for k in EVS:
        hrs = pd.DatetimeIndex(cal.loc[cal["event"] == k, "store_hour"])
        X[f"ev_{k}"] = T.isin(hrs).astype(float)
        X[f"ev_{k}_post"] = T.isin(hrs + pd.Timedelta(hours=1)).astype(float)
    own = own_events(p)
    x["ev_own"] = X[[f"ev_{k}" for k in own]].max(axis=1) if own else 0.0
    x["ev_own_post"] = X[[f"ev_{k}_post" for k in own]].max(axis=1) if own else 0.0
    fcols = ["atr_bp", "prevday_range", "yday_rv", "m5_rv", "m20_rv", "yday_range", "m5_range", "m20_range"]
    ok = X[TERMS].notna().all(axis=1) & x[["l1", "l24", "l120"]].notna().all(axis=1)
    ok &= np.isfinite(x[fcols]).all(axis=1) & (x["range_bp"] > 0) & (x["rv_bp"] > 0) & np.isfinite(x["pipconv"])
    x["lrng"] = np.log(x["range_bp"].where(x["range_bp"] > 0))
    return x, X[TERMS], ok


