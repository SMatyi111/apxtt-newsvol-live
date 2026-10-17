"""Re-fit the News Volatility model on Dukascopy hourly inputs, sanity-check it, and write the frozen coefficient file.

Specification = fx-edge-kit/mt5-news-vol/fit/fit_coefs.py = product_check FULL re-fitted on log high-low range
(see newsvol/model.py). Inputs: <data>/<PAIR>_vol.csv and <PAIR>_ohlc.csv for all 28 G8 pairs (calibration/
fetch_history.py), store clock (NY + 7 h). Event flags: the research calendar events_store_clock.csv (exactly the flags
the original model was fitted with). Rows are filtered like compare.py's okX.

Sanity check ("look A" analogue, all on already-seen data): fit 2018-06-01..2023-12-31 (store clock), score
2024-01-01..2026-10-09 (split at 2026-08-07 like product_check's looks A and B). Two timings:
  lag1 = features from the hour just before the target (the research / indicator timing)
  lag2 = features from data that ends one hour earlier (the live log's timing: a forecast committed before hour T
         starts can only use Dukascopy files up to the end of hour T-2). Baselines get the same data cut.
Production fit (the frozen file): 2018-06-01..2026-10-09, years counter capped at its last fitted value.
Run: python calibration/fit.py --data <dir> --calendar <events_store_clock.csv> --out calibration/output
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from newsvol.calib import frame, load_frames  # noqa: E402
from newsvol.features import MAJORS  # noqa: E402
from newsvol.metrics import losses, nw_t  # noqa: E402
from newsvol.model import TERMS, TERMS_NOF  # noqa: E402

HARD_END = pd.Timestamp("2026-10-10")  # store clock; nothing on/after is read
START = pd.Timestamp("2018-06-01")
FIT_A_END = pd.Timestamp("2024-01-01")
SPLIT_B = pd.Timestamp("2026-08-07")

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True)
ap.add_argument("--calendar", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--coef", default=None, help="path of the coefficient file to write")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

vols, ohlcs = load_frames(a.data, HARD_END)
cal = pd.read_csv(a.calendar, parse_dates=["store_hour"])


def ols(X, y, m, terms):
    b, *_ = np.linalg.lstsq(X.loc[m, terms].values, y[m].values, rcond=None)
    return pd.Series(b, index=terms)


rows, pooled, coef_rows, rep = [], {}, [], []
for lag in (1, 2):
    for p in MAJORS:
        x, X, ok = frame(p, lag, vols, ohlcs, cal)
        y = x["lrng"]
        fit = ok & (x.index < FIT_A_END)
        tst = ok & (x.index >= FIT_A_END) & (x.index < HARD_END)
        b = ols(X, y, fit, TERMS)
        fc = {"FULL": pd.Series(X[TERMS].values @ b.values, index=x.index)}
        for nm, col in (("ATR14_H1", "atr_bp"), ("SameHour20d", "m20_range")):
            lb = np.log(x[col].where(x[col] > 0))
            fc[nm] = lb + (y - lb)[fit].mean()
        for win, m in (("2024-01..2026-08-06", tst & (x.index < SPLIT_B)), ("2026-08-07..10-09", tst & (x.index >= SPLIT_B)),
                       ("2024-01..2026-10-09", tst)):
            L = {nm: losses(x.loc[m, "range_bp"], np.exp(f[m]), x.loc[m, "pipconv"]) for nm, f in fc.items()}
            for grp, gm in (("all", np.ones(m.sum(), bool)), ("own_event_hour", x.loc[m, "ev_own"].values == 1),
                            ("own_event_next_hour", x.loc[m, "ev_own_post"].values == 1)):
                for nm, l in L.items():
                    rows.append(dict(lag=lag, window=win, pair=p, group=grp, model=nm, n=int(gm.sum()),
                                     **{k: float(np.mean(v[gm])) for k, v in l.items()}))
            if win == "2024-01..2026-10-09":
                best = min(("ATR14_H1", "SameHour20d"), key=lambda nm: L[nm]["mse_log"].mean())
                d = pd.Series(L[best]["mse_log"] - L["FULL"]["mse_log"], index=x.index[m])
                rows.append(dict(lag=lag, window=win, pair=p, group="all", model=f"DM_t_vs_{best}", n=int(m.sum()), mse_log=nw_t(d.values, 24)))
                for nm in ("ATR14_H1", "SameHour20d"):
                    dd = pd.Series(L[nm]["mse_log"] - L["FULL"]["mse_log"], index=x.index[m])
                    pooled.setdefault((lag, nm), []).append(dd.rename(p))
        if lag == 1:
            # production fit: everything up to 2026-10-09 (store clock)
            fitP = ok & (x.index < HARD_END)
            bF = ols(X, y, fitP, TERMS)
            bN = ols(X, y, fitP, TERMS_NOF)
            resF = y[fitP] - X.loc[fitP, TERMS] @ bF
            resN = y[fitP] - X.loc[fitP, TERMS_NOF] @ bN
            k_atr = float((y - np.log(x["atr_bp"]))[fitP].mean())
            k_sh = float((y - np.log(x["m20_range"]))[fitP].mean())
            ycap = float(X.loc[fitP, "years"].max())
            for t, v in bF.items():
                coef_rows.append((p, "FULL", t, v))
            for t, v in bN.items():
                coef_rows.append((p, "NOF", t, v))
            for t, v in (("k_atr", k_atr), ("k_sh20", k_sh), ("years_cap", ycap), ("resid_sd_full", float(resF.std())),
                         ("resid_sd_nof", float(resN.std())), ("fit_n", float(fitP.sum()))):
                coef_rows.append((p, "BASE", t, v))
            rep.append(dict(pair=p, fit_n=int(fitP.sum()), fit_first=str(x.index[fitP].min()), fit_last=str(x.index[fitP].max()),
                            resid_sd_full=float(resF.std()), k_atr=k_atr, k_sh20=k_sh, years_cap=ycap))
        print("lag", lag, p, "done", flush=True)

met = pd.DataFrame(rows)
met.to_csv(f"{a.out}/sanity_metrics.csv", index=False)
pool = []
for (lag, nm), lst in pooled.items():
    w = pd.concat(lst, axis=1).mean(axis=1).sort_index()
    pool.append(dict(lag=lag, vs=nm, mean_diff=float(w.mean()), hac_t=nw_t(w.values, 24), n_hours=len(w)))
pool = pd.DataFrame(pool)
pool.to_csv(f"{a.out}/sanity_dm_pooled.csv", index=False)
pd.DataFrame(rep).to_csv(f"{a.out}/fit_report.csv", index=False)

# medians across the 7 majors, as product_check reports medians across pairs
summ = (met[~met.model.str.startswith("DM")].groupby(["lag", "window", "group", "model"])[["n", "mse_log", "qlike", "mae_pips", "hit25"]]
        .median().reset_index())
summ.to_csv(f"{a.out}/sanity_summary.csv", index=False)
pd.set_option("display.width", 250)
print(summ.to_string(index=False))
print(pool.to_string(index=False))

if a.coef:
    assert all(pd.Timestamp(r["fit_last"]) < HARD_END for r in rep)
    with open(a.coef, "w", newline="\n", encoding="ascii") as fh:
        fh.write("# APXTT News Volatility Warning - live-log coefficients (FROZEN). Re-fit on Dukascopy BID M1.\n")
        fh.write(f"# fit window store clock 2018-06-01 00:00 .. {max(r['fit_last'] for r in rep)} (no data on/after 2026-10-10 UTC read)\n")
        fh.write("# target: log of the hour's high-low range in bp (1e4*ln(H/L)); store clock = New York + 7 h\n")
        fh.write("# blocks: FULL (model), NOF (fallback without market factor), BASE (baseline log intercepts k_atr, k_sh20; years_cap)\n")
        fh.write(f"# created {dt.date.today()} by calibration/fit.py\n")
        fh.write("pair,model,term,value\n")
        for p, m, t, v in coef_rows:
            fh.write(f"{p},{m},{t},{np.format_float_positional(float(v), unique=True, trim='0')}\n")
    print("wrote", a.coef, len(coef_rows))
json.dump({"created": str(dt.datetime.utcnow()), "pooled": pool.to_dict("records")}, open(f"{a.out}/sanity_dm_pooled.json", "w"), indent=1)
