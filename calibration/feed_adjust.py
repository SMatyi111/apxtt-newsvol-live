"""Feed check and feed intercepts: the model fitted on the MT5 broker feed, applied to Dukascopy BID M1.

Window (already seen and spent, store clock): 2026-08-07 00:00 .. 2026-10-09 23:00, the product_check "look B" window.
Nothing on or after 2026-10-10 is read.

1. Out-of-sample feed check: coefficients and baseline intercepts fitted on MT5 2018-06-01..2026-08-06 (look B fit),
   scored on the window on BOTH feeds (MT5 and Dukascopy), lag1 (research timing) and lag2 (live timing).
   Same coefficients, same hours: the difference between the two feeds is the feed effect.
2. Feed intercepts for the frozen file: with the production coefficients (MT5, 2018-06..2026-10-09) and the live timing
   (lag2), each forecaster's mean log error on Dukascopy over the window, per pair: d_model, d_atr, d_sh20.
   The live log adds them to the log forecasts. One number per forecaster per pair, the same treatment for all three.
Run: python calibration/feed_adjust.py --duk <dukascopy frames> --mt5 <mt5 frames> --coef <production coef csv>
       --calendar <events_store_clock.csv> --out <dir> --write-coef <frozen coef csv>
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from newsvol.calib import frame, load_frames  # noqa: E402
from newsvol.features import MAJORS  # noqa: E402
from newsvol.metrics import losses, nw_t  # noqa: E402
from newsvol.model import TERMS, read_coefs  # noqa: E402

W0, W1 = pd.Timestamp("2026-08-07"), pd.Timestamp("2026-10-10")
ap = argparse.ArgumentParser()
for k in ("duk", "mt5", "coef", "calendar", "out"):
    ap.add_argument(f"--{k}", required=True)
ap.add_argument("--write-coef", default=None)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
cal = pd.read_csv(a.calendar, parse_dates=["store_hour"])
co = read_coefs(a.coef)
duk = load_frames(a.duk, W1, start_vol=pd.Timestamp("2026-06-01"), start_ohlc=pd.Timestamp("2026-06-01"))
mt5 = load_frames(a.mt5, W1)
mt5_short = load_frames(a.mt5, W1, start_vol=pd.Timestamp("2026-06-01"), start_ohlc=pd.Timestamp("2026-06-01"))

rows, pooled, shifts = [], {}, []
for p in MAJORS:
    # look-B fit on the full MT5 history (lag1 and lag2 frames give the same fit rows up to timing)
    fits = {}
    for lag in (1, 2):
        x, X, ok = frame(p, lag, *mt5, cal)
        y = x["lrng"]
        m = ok & (x.index < W0)
        b, *_ = np.linalg.lstsq(X.loc[m, TERMS].values, y[m].values, rcond=None)
        fits[lag] = (pd.Series(b, index=TERMS), float((y - np.log(x["atr_bp"]))[m].mean()), float((y - np.log(x["m20_range"]))[m].mean()))
    for feed, fr in (("MT5", mt5_short), ("Dukascopy", duk)):
        for lag in (1, 2):
            x, X, ok = frame(p, lag, *fr, cal)
            m = ok & (x.index >= W0) & (x.index < W1)
            y = x.loc[m, "lrng"]
            b, ka, ks = fits[1]  # one set of coefficients (fitted with research timing), applied with both timings
            fc = {"model": X.loc[m, TERMS].values @ b.values, "atr": np.log(x.loc[m, "atr_bp"]) + ka, "sh20": np.log(x.loc[m, "m20_range"]) + ks}
            L = {k: losses(x.loc[m, "range_bp"], np.exp(v), x.loc[m, "pipconv"]) for k, v in fc.items()}
            for grp, gm in (("all", np.ones(m.sum(), bool)), ("own_event_hour", x.loc[m, "ev_own"].values == 1)):
                for k, l in L.items():
                    rows.append(dict(feed=feed, lag=lag, pair=p, group=grp, forecaster=k, n=int(gm.sum()),
                                     mean_log_err=float(np.mean((y.values - np.asarray(fc[k]))[gm])),
                                     **{mm: float(np.mean(v[gm])) for mm, v in l.items()}))
            for k in ("atr", "sh20"):
                d = pd.Series(L[k]["mse_log"] - L["model"]["mse_log"], index=x.index[m])
                pooled.setdefault((feed, lag, k), []).append(d.rename(p))
            if feed == "Dukascopy" and lag == 2:
                # feed intercepts for the production coefficients, live timing
                bP = pd.Series(co[(p, "FULL")])[TERMS]
                B = co[(p, "BASE")]
                Xc = X.loc[m, TERMS].copy()
                Xc["years"] = np.minimum(Xc["years"], B["years_cap"])
                lfm = Xc.values @ bP.values
                d_model = float(np.mean(y.values - lfm))
                d_atr = float(np.mean(y.values - (np.log(x.loc[m, "atr_bp"]) + B["k_atr"])))
                d_sh = float(np.mean(y.values - (np.log(x.loc[m, "m20_range"]) + B["k_sh20"])))
                shifts.append(dict(pair=p, n=int(m.sum()), d_model=d_model, d_atr=d_atr, d_sh20=d_sh))
    print(p, "done", flush=True)

met = pd.DataFrame(rows)
met.to_csv(f"{a.out}/feed_check_metrics.csv", index=False)
pool = []
for (feed, lag, k), lst in pooled.items():
    w = pd.concat(lst, axis=1).mean(axis=1).sort_index()
    pool.append(dict(feed=feed, lag=lag, vs=k, mean_diff=float(w.mean()), hac_t=nw_t(w.values, 24), n_hours=len(w)))
pool = pd.DataFrame(pool)
pool.to_csv(f"{a.out}/feed_check_dm_pooled.csv", index=False)
sh = pd.DataFrame(shifts)
sh.to_csv(f"{a.out}/feed_intercepts.csv", index=False)
summ = met.groupby(["feed", "lag", "group", "forecaster"])[["n", "mean_log_err", "mse_log", "qlike", "mae_pips", "hit25"]].median().reset_index()
summ.to_csv(f"{a.out}/feed_check_summary.csv", index=False)
pd.set_option("display.width", 250)
print(summ.to_string(index=False))
print(pool.to_string(index=False))
print(sh.to_string(index=False))

if a.write_coef:
    lines = open(a.coef, encoding="ascii").read().splitlines()
    head = [l for l in lines if l.startswith("#")]
    body = [l for l in lines if not l.startswith("#")]
    with open(a.write_coef, "w", newline="\n", encoding="ascii") as fh:
        fh.write("# APXTT News Volatility Warning - LIVE LOG COEFFICIENTS (FROZEN 2026-10-17)\n")
        fh.write("# FULL / NOF / BASE k_atr k_sh20 years_cap: production fit on the MT5 broker feed, store clock 2018-06-01 .. 2026-10-09 23:00\n")
        fh.write("#   (identical to fx-edge-kit/mt5-news-vol apxtt_newsvol_coefs.csv, max diff < 1e-14)\n")
        fh.write("# BASE d_model d_atr d_sh20: Dukascopy feed intercepts (live timing), mean log error on Dukascopy BID M1,\n")
        fh.write("#   store hours 2026-08-07 .. 2026-10-09 (calibration/feed_adjust.py). Live log forecast = exp(lf + d).\n")
        fh.write("# Nothing on or after 2026-10-10 00:00 UTC was read.\n")
        for l in body:
            fh.write(l + "\n")
        for r in shifts:
            for k in ("d_model", "d_atr", "d_sh20"):
                fh.write(f"{r['pair']},BASE,{k},{np.format_float_positional(r[k], unique=True, trim='0')}\n")
    print("wrote", a.write_coef)
