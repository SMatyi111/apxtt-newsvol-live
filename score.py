"""Append realised ranges for forecast hours that have ended, then rebuild scoreboard.json.

Realised range = max - min of the Dukascopy BID price over the UTC hour (hour tick file), in bp = 1e4 ln(H/L).
An hour is scoreable when (PREREGISTRATION.md): the forecast record exists, it was pushed before the hour started
(receipt in log/receipts.jsonl), the hour has >= 50 one-minute BID returns, and all three forecasters have a number.
Hours whose tick file is still missing are retried on later runs; after 72 h they are written as missing.
Run: python score.py [--now 2026-10-19T05:40]
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsvol.dukascopy import NotPublished  # noqa: E402
from newsvol.features import MAJORS  # noqa: E402
from newsvol.live import (FORECASTS, LOG_START, LogCorrupt, REALIZED, RECEIPTS, SCOREBOARD, SEALED, append_chained, frozen_hashes,  # noqa: E402
                          iso, new_fetcher, read_jsonl, realized_hour, utcnow, verify_chain)
from newsvol.metrics import losses, nw_t  # noqa: E402

READ_DATE = dt.datetime(2026, 12, 14)  # first formal evaluation: hours 2026-10-19 00:00 .. 2026-12-13 23:00 UTC
MIN_HOURS = 600
MODELS = {"model": "f_model_bp", "atr": "f_atr_bp", "sh20": "f_sh20_bp"}


def parse(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def collect_realized(now, log=print):
    fc = read_jsonl(FORECASTS)
    have = {r["target_hour_utc"] for r in read_jsonl(REALIZED)}
    f = new_fetcher(log=log)
    f.waits, f.timeout = [3, 10, 20, 40], 25
    added = 0
    for r in fc:
        T = parse(r["target_hour_utc"])
        if r["target_hour_utc"] in have or T < LOG_START or SEALED[0] <= T < SEALED[1]:
            continue
        if T + dt.timedelta(hours=1) > now:
            continue
        pairs, missing = {}, False
        for p in MAJORS:
            try:
                pairs[p] = realized_hour(f, p, T)
            except NotPublished:
                missing = True
                break
            except Exception as e:  # network trouble: retry on a later run
                log(f"  {p} {r['target_hour_utc']}: {e!r}; retry later")
                missing = True
                break
        if missing:
            if now - T > dt.timedelta(hours=72):
                append_chained(REALIZED, {"target_hour_utc": r["target_hour_utc"], "status": "missing_after_72h",
                                          "fetched_utc": iso(now), "pairs": {}})
                added += 1
            continue
        append_chained(REALIZED, {"target_hour_utc": r["target_hour_utc"], "status": "ok", "fetched_utc": iso(now),
                                  "source": "Dukascopy BID ticks (hourly file)", "pairs": pairs})
        added += 1
    log(f"realised records added: {added}; requests {f.n_requests}")
    return added


def timing():
    """target -> earliest confirmed push time of the commit that added the forecast."""
    out = {}
    for r in read_jsonl(RECEIPTS):
        t = r.get("target_hour_utc")
        if t and r.get("pushed_utc"):
            out[t] = min(out.get(t, r["pushed_utc"]), r["pushed_utc"])
    return out


def build_scoreboard(now):
    fc = {r["target_hour_utc"]: r for r in read_jsonl(FORECASTS) if r.get("mode") == "live"}
    rz = {r["target_hour_utc"]: r for r in read_jsonl(REALIZED)}
    tm = timing()
    rows, last = [], []
    n_late = n_missing_receipt = 0
    for t, r in sorted(fc.items()):
        T = parse(t)
        pushed = tm.get(t)
        on_time = pushed is not None and parse(pushed) < T
        if pushed is None:
            n_missing_receipt += 1
        elif not on_time:
            n_late += 1
        z = rz.get(t)
        for p in MAJORS:
            f = r["pairs"].get(p, {})
            y = (z or {}).get("pairs", {}).get(p, {})
            row = dict(target=t, pair=p, on_time=on_time, pushed_utc=pushed, status=f.get("status"),
                       own_event=f.get("own_event_hour", 0), own_event_next=f.get("own_event_next_hour", 0),
                       **{k: f.get(c) for k, c in MODELS.items()},
                       y_bp=y.get("range_bp"), valid=y.get("valid", 0), pipconv=y.get("pipconv"),
                       f_model_pips=f.get("f_model_pips"), f_atr_pips=f.get("f_atr_pips"), f_sh20_pips=f.get("f_sh20_pips"),
                       y_pips=y.get("range_pips"), events=",".join(r.get("events", [])))
            rows.append(row)
    df = pd.DataFrame(rows)
    board = {"generated_utc": iso(now), "log_start_utc": iso(LOG_START), "first_formal_read_utc": iso(READ_DATE),
             "pairs": MAJORS, **frozen_hashes(),
             "chains_ok": {"forecasts": verify_chain(FORECASTS)[0], "realized": verify_chain(REALIZED)[0]},
             "forecast_hours": len(fc), "late_hours": n_late, "hours_without_receipt": n_missing_receipt,
             "status": "waiting" if not len(df) else "live"}
    if len(df):
        ok = df["on_time"] & (df["valid"] == 1) & df["status"].eq("ok") & df[["model", "atr", "sh20", "y_bp", "pipconv"]].notna().all(axis=1)
        sc = df[ok].copy()
        board["hours_scored"] = int(sc["target"].nunique())
        board["pair_hours_scored"] = int(len(sc))

        def block(s):
            if not len(s):
                return {"n": 0}
            res = {"n": int(len(s)), "hours": int(s["target"].nunique()), "mean_range_pips": float(np.mean(s["y_bp"] * s["pipconv"]))}
            for k in MODELS:
                L = losses(s["y_bp"], s[k], s["pipconv"])
                res[k] = {m: float(np.mean(v)) for m, v in L.items()}
            return res

        def dm(s):
            if not len(s):
                return {}
            out = {}
            Lm = losses(s["y_bp"], s["model"], s["pipconv"])["mse_log"]
            for k in ("atr", "sh20"):
                d = pd.Series(losses(s["y_bp"], s[k], s["pipconv"])["mse_log"] - Lm, index=s.index)
                w = d.groupby(s["target"].values).mean().sort_index()
                out[k] = {"mean_diff": float(w.mean()), "hac_t_lag24": nw_t(w.values, 24), "n_hours": int(len(w))}
            return out

        allb = block(sc)
        rel = sc[sc["own_event"] == 1]
        board["all_hours"] = allb
        board["release_hours"] = block(rel)
        board["release_next_hours"] = block(sc[sc["own_event_next"] == 1])
        board["per_pair"] = {p: block(sc[sc["pair"] == p]) for p in MAJORS}
        board["dm_pooled_mse_log"] = dm(sc)
        def primary(s):
            b = block(s)
            if not b["n"]:
                return None
            best = min(("atr", "sh20"), key=lambda k: b[k]["mse_log"])
            d = dm(s)[best]
            t = d["hac_t_lag24"]
            if b["hours"] < MIN_HOURS:
                reading = "not enough hours yet"
            elif b["model"]["mse_log"] >= b[best]["mse_log"]:
                reading = "FAIL"
            elif t is not None and np.isfinite(t) and t > 1.96:
                reading = "PASS"
            else:
                reading = "INDETERMINATE"
            return {"best_free_baseline": best, "model_mse_log": b["model"]["mse_log"], "baseline_mse_log": b[best]["mse_log"],
                    "mse_ratio": b["model"]["mse_log"] / b[best]["mse_log"], "hac_t": t, "hours": b["hours"], "reading_if_read_now": reading}

        board["primary_running"] = primary(sc)
        if now >= READ_DATE:
            board["formal_read"] = primary(sc[pd.to_datetime(sc["target"], format="%Y-%m-%dT%H:%M:%SZ") < READ_DATE])
        board["pass_rule"] = ("PASS if, over scored hours 2026-10-19 00:00 .. 2026-12-13 23:00 UTC, the model's pooled MSE-log is lower "
                              "than the best free baseline's and the pooled Diebold-Mariano HAC t (lag 24) > 1.96; FAIL if not lower; "
                              f"else INDETERMINATE (needs >= {MIN_HOURS} scored hours)")
    recent = sorted(fc)[-24:]
    board["last_forecasts"] = []
    for t in reversed(recent):
        r = fc[t]
        z = rz.get(t, {})
        board["last_forecasts"].append({
            "target_hour_utc": t, "events": r.get("events", []), "on_time": (tm.get(t) is not None and parse(tm[t]) < parse(t)),
            "pairs": {p: {"model": r["pairs"].get(p, {}).get("f_model_pips"), "atr": r["pairs"].get(p, {}).get("f_atr_pips"),
                          "sh20": r["pairs"].get(p, {}).get("f_sh20_pips"),
                          "actual": (z.get("pairs", {}).get(p, {}) or {}).get("range_pips") if z else None}
                      for p in MAJORS}})
    board = _clean(board)  # A1: NaN/inf (e.g. the HAC t with < 10 scored hours) -> null; this crashed every run
    with open(SCOREBOARD, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(board, fh, indent=1, sort_keys=False, allow_nan=False, default=lambda o: None)
        fh.write("\n")
    return board


def _clean(o):
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", default=None)
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.now) if a.now else utcnow()
    # A1 preflight: every log line must be a valid JSON object and both chains intact; otherwise stop loudly
    # (exit 3) and write nothing. Past lines are never dropped, rewritten or repaired by this script.
    try:
        for path in (FORECASTS, REALIZED, RECEIPTS):
            read_jsonl(path)
        for path in (FORECASTS, REALIZED):
            ok, bad = verify_chain(path)
            if not ok:
                raise LogCorrupt(f"{path}: hash chain broken at record {bad}")
        old = json.load(open(SCOREBOARD, encoding="utf-8")) if os.path.exists(SCOREBOARD) else {}
    except (LogCorrupt, json.JSONDecodeError) as e:
        print(f"LOG CORRUPT, nothing written: {e}", file=sys.stderr)
        sys.exit(3)
    if not a.no_fetch:
        collect_realized(now)
    b = build_scoreboard(now)
    b = _clean(b)
    if {k: v for k, v in old.items() if k != "generated_utc"} == {k: v for k, v in b.items() if k != "generated_utc"}:
        b = old  # nothing new: keep the file unchanged (no empty commits)
    with open(SCOREBOARD, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(b, fh, indent=1)
        fh.write("\n")
    print("scoreboard:", b.get("status"), "hours scored", b.get("hours_scored", 0))
