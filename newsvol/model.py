"""The frozen model: coefficient file I/O, the regressor vector, and the three forecasters scored in the live log.

FULL (product_check FULL = fx-vol-seasonality's M_B, re-fitted on log high-low range):
  log range_bp(T) = const + hour(23) + weekday(4) + month(11) dummies on the store clock + b*years (capped)
                    + HAR-CJ state (c1 c24 c120 lj1 jf24 lj24) + market factor (f1 f24)
                    + 12 events x (event hour, hour after)
NOF = the same without the market factor (used only if the factor cannot be computed).
Free baselines, each with ONE log intercept k fitted on the calibration window (product_check: "k x ATR"):
  ATR14_H1 : k_atr * ATR(14) on H1 (Wilder, true range) of the last complete hour, in bp of that hour's close
  SameHour20d : k_sh20 * mean range of the same store hour over the previous 20 valid trading days (min 12)
"""
import hashlib

import numpy as np
import pandas as pd

EVS = ["nfp", "cpi", "fomc", "ecb", "boe", "claims", "ppi", "ism", "boc", "rba", "snb", "boj"]
EVCUR = {"nfp": "USD", "cpi": "USD", "fomc": "USD", "claims": "USD", "ppi": "USD", "ism": "USD", "ecb": "EUR",
         "boe": "GBP", "boc": "CAD", "rba": "AUD", "snb": "CHF", "boj": "JPY"}
HAR = ["c1", "c24", "c120", "lj1", "jf24", "lj24"]
FAC = ["f1", "f24"]
TERMS = (["const"] + [f"h_{i}" for i in range(1, 24)] + [f"w_{i}" for i in range(2, 6)] + [f"m_{i}" for i in range(2, 13)]
         + ["years"] + HAR + FAC + [c for k in EVS for c in (f"ev_{k}", f"ev_{k}_post")])
TERMS_NOF = [t for t in TERMS if t not in FAC]


def own_events(pair):
    return [k for k in EVS if EVCUR[k] in (pair[:3], pair[3:])]


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_coefs(path):
    """-> {(pair, block): {term: value}} ; blocks FULL, NOF, BASE (k_atr, k_sh20, years_cap, resid_sd ...)."""
    co = {}
    with open(path, encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("pair,"):
                continue
            p, m, t, v = line.split(",")
            co.setdefault((p, m), {})[t] = float(v)
    return co


def regressors(store_hour, feats, flags, years_cap, with_factor=True):
    """Regressor dict for target store hour (naive Timestamp on the store clock)."""
    x = {t: 0.0 for t in (TERMS if with_factor else TERMS_NOF)}
    x["const"] = 1.0
    if store_hour.hour >= 1:
        x[f"h_{store_hour.hour}"] = 1.0
    wd = store_hour.dayofweek + 1
    if wd >= 2:
        x[f"w_{wd}"] = 1.0
    if store_hour.month >= 2:
        x[f"m_{store_hour.month}"] = 1.0
    years = (store_hour - pd.Timestamp("2018-06-01")).total_seconds() / (365.25 * 86400)
    x["years"] = min(years, years_cap)
    for k in HAR + (FAC if with_factor else []):
        x[k] = float(feats[k])
    for k, v in flags.items():
        x[k] = float(v)
    return x


def predict(coef, x):
    return float(sum(coef[t] * v for t, v in x.items()))
