"""Shared live-log machinery: constants, data loading from Dukascopy, hash-chained JSONL logs."""
import datetime as dt
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .dukascopy import Fetcher, NotPublished
from .features import G8, MAJORS, add_factor, asof, hourly_from_m1, pip_size, same_hour_mean, state, utc_to_store
from .model import EVS, own_events, predict, read_coefs, regressors, sha256_file
from .events import flags_for, read_events

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COEF = os.path.join(ROOT, "model", "coefficients.csv")
EVENTS = os.path.join(ROOT, "model", "events_utc.csv")
LOG = os.path.join(ROOT, "log")
FORECASTS = os.path.join(LOG, "forecasts.jsonl")
REALIZED = os.path.join(LOG, "realized.jsonl")
RECEIPTS = os.path.join(LOG, "receipts.jsonl")
WARMUP = os.path.join(LOG, "warmup.jsonl")
SCOREBOARD = os.path.join(ROOT, "scoreboard.json")
CACHE = os.environ.get("NEWSVOL_CACHE", os.path.join(ROOT, "cache"))

LOG_START = dt.datetime(2026, 10, 19)            # first scored hour (UTC)
SEALED = (dt.datetime(2026, 10, 10), dt.datetime(2026, 10, 19))  # one-shot confirmation window: never a target here
OWN_DAYS, OTHER_DAYS = 35, 5                    # calendar days of M1 history loaded per run
MIN_VALID_RETURNS = 50


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso(t):
    return None if t is None else pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------------- logs
def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canon(rec):
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def append_chained(path, rec):
    """Append rec with prev_hash (hash of the previous line's record) and hash = sha256 of the canonical record
    without the 'hash' field. Returns the stored record."""
    prev = read_jsonl(path)
    rec = dict(rec)
    rec["prev_hash"] = prev[-1]["hash"] if prev else "0" * 64
    rec.pop("hash", None)
    rec["hash"] = hashlib.sha256(canon(rec).encode()).hexdigest()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(canon(rec) + "\n")
    return rec


def verify_chain(path):
    prev = "0" * 64
    for i, r in enumerate(read_jsonl(path)):
        h = r.get("hash")
        body = {k: v for k, v in r.items() if k != "hash"}
        if r.get("prev_hash") != prev or hashlib.sha256(canon(body).encode()).hexdigest() != h:
            return False, i
        prev = h
    return True, None


# ---------------------------------------------------------------------------------------------------- data
def load_m1(fetcher, pair, first_day, now, hard_end=None):
    """M1 BID bars from first_day (UTC date) up to the last complete hour published before `now`.
    Past days use the day candle file; a day whose file is not published yet (today, sometimes yesterday) is
    filled hour by hour from tick files, stopping at the first hour that is missing. Returns (m1, data_until):
    data_until = exclusive UTC end of contiguous data (naive datetime)."""
    parts = []
    day = first_day
    data_until = dt.datetime(first_day.year, first_day.month, first_day.day)
    stop = now if hard_end is None else min(now, hard_end)
    while dt.datetime(day.year, day.month, day.day) < stop:
        d0 = dt.datetime(day.year, day.month, day.day)
        got_day = False
        if d0 + dt.timedelta(days=1) <= stop:
            try:
                parts.append(fetcher.day_candles(pair, day, now_utc=now))
                data_until = d0 + dt.timedelta(days=1)
                got_day = True
            except NotPublished:
                pass
            except Exception as e:  # network failure: keep what we have, data ends here
                fetcher.log(f"  {pair} {day}: {e!r}; data ends at {data_until}")
                break
        if not got_day:
            if d0.weekday() == 5:  # Saturday UTC: FX closed, no files to expect
                data_until = min(d0 + dt.timedelta(days=1), stop)
                day += dt.timedelta(days=1)
                continue
            h = d0
            while h + dt.timedelta(hours=1) <= stop:
                if utc_to_store(h).weekday() >= 5:  # FX closed (store-clock weekend): nothing to fetch
                    h += dt.timedelta(hours=1)
                    data_until = h
                    continue
                try:
                    parts.append(fetcher.hour_ticks_m1(pair, h))
                except NotPublished:
                    break
                except Exception as e:
                    fetcher.log(f"  {pair} {h}: {e!r}; data ends at {data_until}")
                    break
                h += dt.timedelta(hours=1)
                data_until = h
            if h + dt.timedelta(hours=1) <= stop:  # an hour is missing: data ends here
                break
        day += dt.timedelta(days=1)
    m1 = np.concatenate(parts) if parts else np.empty(0, dtype=[("t", "i8"), ("o", "f8"), ("h", "f8"), ("l", "f8"), ("c", "f8"), ("v", "f8")])
    m1 = m1[np.argsort(m1["t"], kind="stable")]
    return m1, data_until


def make_forecasts(fetcher, target_utc, now, log=print):
    """Forecasts for the hour starting at target_utc using everything published before `now`. Returns dict."""
    co = read_coefs(COEF)
    events = read_events(EVENTS)
    tstore = pd.Timestamp(utc_to_store(target_utc))
    vols, ohlcs, until = {}, {}, {}

    def one(p):
        fp = Fetcher(fetcher.cache, min_gap=fetcher.min_gap, log=log, waits=(3, 10, 20, 40), timeout=25)
        days = OWN_DAYS if p in MAJORS else OTHER_DAYS
        first = (target_utc - dt.timedelta(days=days)).date()
        m1, du = load_m1(fp, p, first, now, hard_end=target_utc)
        return p, m1, du, fp.n_requests, fp.n_429

    with ThreadPoolExecutor(max_workers=int(os.environ.get("NEWSVOL_THREADS", "6"))) as ex:
        for p, m1, du, nreq, n429 in ex.map(one, G8):
            vols[p], ohlcs[p] = hourly_from_m1(m1)
            until[p] = du
            fetcher.n_requests += nreq
            fetcher.n_429 += n429
    add_factor(vols)
    flags = flags_for(events, target_utc)
    out = {}
    for p in MAJORS:
        b = co[(p, "BASE")]
        v, o = vols[p], ohlcs[p]
        rec = {"data_until": iso(until[p])}
        if len(v) < 130 or len(o) < 30:
            rec["status"] = "no_forecast_insufficient_data"
            out[p] = rec
            continue
        s, at = state(v, o)
        D = pd.Timestamp(utc_to_store(until[p]))  # store clock
        st = asof(s, [D]).iloc[0]
        a = asof(at, [D]).iloc[0]
        need = ["c1", "c24", "c120", "lj1", "jf24", "lj24"]
        if not np.all(np.isfinite(st[need].astype(float))):
            rec["status"] = "no_forecast_insufficient_data"
            out[p] = rec
            continue
        full = bool(np.isfinite(st["f1"]) and np.isfinite(st["f24"]))
        x = regressors(tstore, st, flags, b["years_cap"], with_factor=full)
        lf = predict(co[(p, "FULL" if full else "NOF")], x) + b["d_model"]
        close = float(a["close"])
        conv = close / 1e4 / pip_size(p)
        atr_bp = float(a["atr_bp"]) * np.exp(b["k_atr"] + b["d_atr"])
        sh = same_hour_mean(v, o, tstore)
        sh_bp = sh * np.exp(b["k_sh20"] + b["d_sh20"]) if np.isfinite(sh) else None
        own = own_events(p)
        rec.update({
            "status": "ok",
            "model": "FULL" if full else "NOF",
            "f_model_bp": round(float(np.exp(lf)), 6),
            "f_atr_bp": round(atr_bp, 6),
            "f_sh20_bp": None if sh_bp is None else round(float(sh_bp), 6),
            "f_model_pips": round(float(np.exp(lf)) * conv, 3),
            "f_atr_pips": round(atr_bp * conv, 3),
            "f_sh20_pips": None if sh_bp is None else round(float(sh_bp) * conv, 3),
            "ref_close": close,
            "last_complete_hour_utc": iso(until[p] - dt.timedelta(hours=1)),
            "features_lag_hours": int(round((target_utc - until[p]).total_seconds() / 3600)) + 1,
            "own_event_hour": int(any(flags[f"ev_{k}"] for k in own)),
            "own_event_next_hour": int(any(flags[f"ev_{k}_post"] for k in own)),
        })
        out[p] = rec
    active = [k for k, val in flags.items() if val]
    return {"pairs": out, "events": active, "store_hour": tstore.strftime("%Y-%m-%d %H:%M")}


def realized_hour(fetcher, pair, target_utc):
    """Realised range of the UTC hour from Dukascopy BID ticks (hour file of target, plus the previous hour for the
    first one-minute return and the reference close). Raises NotPublished if the target hour's file is missing."""
    cur = fetcher.hour_ticks_m1(pair, target_utc)
    try:
        prev = fetcher.hour_ticks_m1(pair, target_utc - dt.timedelta(hours=1))
    except NotPublished:
        prev = cur[:0]
    m1 = np.concatenate([prev, cur])
    if len(cur) == 0:
        return {"valid": 0, "n_ret": 0, "n_min": 0}
    t = m1["t"]
    r_ok = np.r_[False, (t[1:] - t[:-1]) == 60]
    in_hour = t >= int(target_utc.replace(tzinfo=dt.timezone.utc).timestamp())
    lc = np.log(m1["c"])
    r = np.r_[np.nan, np.diff(lc)]
    good = r_ok & in_hour & np.isfinite(r)
    rv = float(np.sum(r[good] ** 2))
    n_ret = int(good.sum())
    hi, lo = float(cur["h"].max()), float(cur["l"].min())
    close_prev = float(prev["c"][-1]) if len(prev) else None
    rng_bp = 1e4 * np.log(hi / lo)
    store_wd = utc_to_store(target_utc).weekday()
    valid = int(n_ret >= MIN_VALID_RETURNS and rv > 0 and rng_bp > 0 and close_prev is not None and store_wd <= 4)
    return {"valid": valid, "n_ret": n_ret, "n_min": int(len(cur)), "high": hi, "low": lo,
            "range_bp": round(rng_bp, 6), "range_pips": round((hi - lo) / pip_size(pair), 3),
            "close_prev": close_prev, "pipconv": None if close_prev is None else close_prev / 1e4 / pip_size(pair)}


def new_fetcher(log=print, budget=None):
    return Fetcher(CACHE, min_gap=float(os.environ.get("NEWSVOL_GAP", "0.4")), budget=budget, log=log)


def frozen_hashes():
    return {"coefficients_sha256": sha256_file(COEF), "events_sha256": sha256_file(EVENTS)}
