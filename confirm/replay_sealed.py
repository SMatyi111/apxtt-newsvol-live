"""Replay harness for the sealed confirmation week 2026-10-10 00:00 .. 2026-10-18 23:59 UTC.

Binding text: CONFIRMATION_PREREG.md (tag confirm-v1), sections 5, 8 and 10. This file is pinned there by sha256.

Modes (python confirm/replay_sealed.py <mode>):
  targets   List the target hours of the sealed week with the frozen store clock. Calendar only: no price, no network.
  selftest  Pre-read test on already-seen data. Replays the frozen pipeline at as-of 2026-10-07 13:35 UTC for the
            target hour 14:00 UTC and checks that it reproduces the warm-up record in log/warmup.jsonl exactly
            (forecasts, input coverage, event flags, and the realised-range path). It may request only files that end
            on or before 2026-10-10 00:00 UTC, whatever the date.
  read      The one-shot read. Refused before 2026-12-14 00:00 UTC. For every target hour T it calls the frozen
            make_forecasts(fetcher, T, now = T - 25 min) and the frozen realized_hour(fetcher, pair, T), writes
            hash-chained records, then computes the fixed reading (score.py primary() logic, prereg section 8).
            Resumable after a crash that produced no reading; refused once a reading exists.
  status    Counts only (records written, reading present or not). Prints no forecast or outcome value.

Guards (installed when this module is imported, so every mode and every importer gets them):
  G1  Every Dukascopy file access, from the network AND from the on-disk cache, goes through
      newsvol.dukascopy.Fetcher._cached. That method is wrapped here at class level, so every Fetcher instance is
      covered, including the ones make_forecasts creates in its worker threads. A file whose UTC span overlaps
      2026-10-10 00:00 .. 2026-10-19 00:00 raises SealedWindowRefusal while the UTC clock is before 2026-12-14 00:00.
      A file name that cannot be parsed is refused too (fail closed). SealedWindowRefusal derives from BaseException,
      so the frozen loader's `except Exception` cannot swallow it into a shorter data series.
  G2  In selftest mode every file that ends after 2026-10-10 00:00 is refused, whatever the date.
  G3  `read` refuses to start before 2026-12-14 00:00 UTC by the local clock (checked before anything else), and then
      also by the HTTP Date header of datafeed.dukascopy.com (refused if it cannot be read). It also refuses if a
      frozen file differs from its pinned sha256, if this file's sha256 is not written in CONFIRMATION_PREREG.md, if
      a reading already exists, or if another read holds the lock.
  G4  A fetch failure other than HTTP 404 raises ReplayFetchAbort (a BaseException) instead of letting the frozen
      loader end the data early. The target is retried; a rerun resumes from the cache and the chained records.
There is no option to override the clock.

Raw Dukascopy files go to a private cache outside the repository (env NEWSVOL_REPLAY_CACHE, default
~/.cache/apxtt-newsvol-replay). They are never committed (Dukascopy licence).
"""
import argparse
import datetime as dt
import email.utils
import hashlib
import json
import os
import platform
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from newsvol import dukascopy as _dk  # noqa: E402
from newsvol import live as _live  # noqa: E402
from newsvol.features import MAJORS, utc_to_store  # noqa: E402
from newsvol.metrics import losses, nw_t  # noqa: E402

# ------------------------------------------------------------------------------------------------ fixed constants
SEALED = (dt.datetime(2026, 10, 10), dt.datetime(2026, 10, 19))   # [start, end) UTC
READ_NOT_BEFORE = dt.datetime(2026, 12, 14)                       # UTC; the read and any sealed file before it: refused
DATA_DEADLINE = dt.datetime(2027, 1, 12)                          # replay not finished by 2027-01-11 -> NOT READ
REPLAY_LEAD = dt.timedelta(minutes=25)                            # now = T - 25 min (minute 35 of the hour before)
N_TARGETS = 123
MIN_HOURS = 600                                                   # live prereg; below it the reading is UNDERPOWERED
SELFTEST_TARGET = dt.datetime(2026, 10, 7, 14)
SELFTEST_ASOF = dt.datetime(2026, 10, 7, 13, 35)
SELFTEST_REF_HASH = "8899502778f6f8cc59b4d7494a8fe74d8a553f6469954a60adcfb622a299f2f6"   # newest warm-up record
SELFTEST_REF2_HASH = "4356775e35654a1c9f809c7d17c79f10665022ca99046e7b07dbfbfef70e8272"  # earlier record, same code path

# sha256 of the frozen files (blobs of commit 8b092db; CONFIRMATION_PREREG.md section 2)
FROZEN = {
    "model/coefficients.csv": "21663b2aedcd6ecec87a6d13f482b4c4d87adb2ae261d1a9eb035a5c8d18ced4",
    "model/events_utc.csv": "da1da082e25f011829ac4320144098b84dc82e891328ff31be8acef7bbb65e1b",
    "PREREGISTRATION.md": "bffc98dff566d29f3211fb23bacc632d0a33f9e198cac5516b1a3fee49b6ffa4",
    "newsvol/live.py": "5845e419dcc7454ebd9d94c1fb3f5257b0dfd35191017619bc852eb21617d9cb",
    "newsvol/features.py": "44ed121ae8b93e92b460cc6053e7a62659011088c9540b2eb420ed93b0ff76e6",
    "newsvol/model.py": "5931efdd4c29ebb719bf70d963148bedad86a45d559b13f2738d2c59bf4889d9",
    "newsvol/events.py": "85b63e8e9d3eae8bfd23d46fd1ee437d1f0313da6eafd1067c2bc382c947e8c3",
    "newsvol/metrics.py": "0368b928dd24d16244957a42ef954fe8c1059166769ff02dca8e9295ca6d17df",
    "newsvol/dukascopy.py": "0c04cb73d28250437c18d757752d7546019f8d3a59e7b508989bc000b294f623",
    "score.py": "2ca4536480d089db40b8ad4b58e8438d7fdd210520b46b46503d39340a059424",
}
PREREG = os.path.join(ROOT, "CONFIRMATION_PREREG.md")
OUT = os.path.join(HERE, "sealed_read")
FC_OUT = os.path.join(OUT, "forecasts_sealed.jsonl")
RZ_OUT = os.path.join(OUT, "realized_sealed.jsonl")
READING_OUT = os.path.join(OUT, "reading_sealed.json")
LOCK = os.path.join(OUT, "read.lock")
CACHE = os.environ.get("NEWSVOL_REPLAY_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "apxtt-newsvol-replay"))
MODELS = {"model": "f_model_bp", "atr": "f_atr_bp", "sh20": "f_sh20_bp"}   # as score.py


class SealedWindowRefusal(BaseException):
    """A sealed-week file (or the read itself) was requested before 2026-12-14 00:00 UTC. Never caught here."""


class ReplayFetchAbort(BaseException):
    """A non-404 fetch failure. Aborts the target instead of letting the frozen loader truncate the inputs."""


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def iso(t):
    return _live.iso(t)


def log(msg):
    print(f"{utcnow():%Y-%m-%dT%H:%M:%SZ} {msg}", file=sys.stderr, flush=True)


def sha256_path(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def harness_sha256():
    return sha256_path(os.path.abspath(__file__))


# ------------------------------------------------------------------------------------------------ guard (G1, G2, G4)
_REL = re.compile(r"^([A-Z]{6})/(\d{4})/(\d{2})/(\d{2})/(?:BID_candles_min_1|(\d{2})h_ticks)\.bi5$")
GUARD = {"seen_only": False}       # G2 switch (selftest)
ACCESSED = set()                   # every rel path that passed the guard in this process


def file_span(rel):
    """UTC [start, end) covered by a Dukascopy file path; ValueError if the name is not one of the two known kinds."""
    m = _REL.match(rel)
    if not m:
        raise ValueError(f"unknown Dukascopy file name: {rel!r}")
    _, y, m0, d, hh = m.groups()
    day = dt.datetime(int(y), int(m0) + 1, int(d))
    if hh is None:
        return day, day + dt.timedelta(days=1)
    start = day + dt.timedelta(hours=int(hh))
    return start, start + dt.timedelta(hours=1)


def check_rel(rel, now=None, seen_only=None):
    """Raise SealedWindowRefusal if this file may not be read now. `now` and `seen_only` are parameters only so the
    tests can probe the rule; the installed guard always passes the real UTC clock."""
    now = utcnow() if now is None else now
    seen_only = GUARD["seen_only"] if seen_only is None else seen_only
    try:
        a, b = file_span(rel)
    except ValueError as e:
        raise SealedWindowRefusal(f"refused (fail closed): {e}") from None
    if seen_only and b > SEALED[0]:
        raise SealedWindowRefusal(f"refused: self-test may read only files ending by {iso(SEALED[0])}: {rel}")
    if a < SEALED[1] and b > SEALED[0] and now < READ_NOT_BEFORE:
        raise SealedWindowRefusal(f"refused: {rel} overlaps the sealed week and the clock ({iso(now)}) is before "
                                  f"{iso(READ_NOT_BEFORE)}")


_ORIG_CACHED = _dk.Fetcher._cached


def _guarded_cached(self, rel, cache_empty):
    check_rel(rel)
    ACCESSED.add(rel)
    try:
        return _ORIG_CACHED(self, rel, cache_empty)
    except _dk.NotPublished:
        raise
    except Exception as e:  # noqa: BLE001  (G4: do not let the frozen loader end the data early)
        raise ReplayFetchAbort(f"{rel}: {e!r}") from e


if not getattr(_dk.Fetcher._cached, "_sealed_guard", False):
    _guarded_cached._sealed_guard = True
    _dk.Fetcher._cached = _guarded_cached
assert _live.Fetcher is _dk.Fetcher and _live.SEALED == SEALED  # make_forecasts builds this same (guarded) class


def new_fetcher():
    os.makedirs(CACHE, exist_ok=True)
    return _dk.Fetcher(CACHE, min_gap=float(os.environ.get("NEWSVOL_GAP", "0.4")), log=log)


# ------------------------------------------------------------------------------------------------ checks
def frozen_check():
    bad = {f: sha256_path(os.path.join(ROOT, f)) for f in FROZEN if sha256_path(os.path.join(ROOT, f)) != FROZEN[f]}
    return bad


def sealed_targets():
    """Every UTC hour of the sealed week that falls in the FX week (store clock Mon 00:00 .. Fri 23:59)."""
    out, t = [], SEALED[0]
    while t < SEALED[1]:
        if utc_to_store(t).weekday() <= 4:
            out.append(t)
        t += dt.timedelta(hours=1)
    return out


def server_utc(timeout=20):
    """UTC time from the HTTP Date header of datafeed.dukascopy.com (no data file is requested). None if unreadable."""
    for host in _dk.HOSTS:
        req = urllib.request.Request(host + "/", method="HEAD", headers={"User-Agent": _dk.UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = r.headers.get("Date")
        except urllib.error.HTTPError as e:
            d = e.headers.get("Date") if e.headers else None
        except Exception:  # noqa: BLE001
            continue
        if d:
            try:
                return email.utils.parsedate_to_datetime(d).astimezone(dt.timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                continue
    return None


# ------------------------------------------------------------------------------------------------ reading (section 8)
def build_rows(fc_records, rz_records):
    """Pair-hour rows exactly as score.py build_scoreboard(), minus the push-receipt timing (replaced by the replay
    timing rule, prereg section 5)."""
    fc = {r["target_hour_utc"]: r for r in fc_records}
    rz = {r["target_hour_utc"]: r for r in rz_records}
    rows = []
    for t, r in sorted(fc.items()):
        z = rz.get(t)
        for p in MAJORS:
            f = r["pairs"].get(p, {})
            y = (z or {}).get("pairs", {}).get(p, {})
            rows.append(dict(target=t, pair=p, status=f.get("status"),
                             own_event=f.get("own_event_hour", 0), own_event_next=f.get("own_event_next_hour", 0),
                             **{k: f.get(c) for k, c in MODELS.items()},
                             y_bp=y.get("range_bp"), valid=y.get("valid", 0), pipconv=y.get("pipconv"),
                             lag=f.get("features_lag_hours")))
    return pd.DataFrame(rows)


def _block(s):  # score.py block()
    if not len(s):
        return {"n": 0}
    res = {"n": int(len(s)), "hours": int(s["target"].nunique()), "mean_range_pips": float(np.mean(s["y_bp"] * s["pipconv"]))}
    for k in MODELS:
        L = losses(s["y_bp"], s[k], s["pipconv"])
        res[k] = {m: float(np.mean(v)) for m, v in L.items()}
    return res


def _dm(s):  # score.py dm()
    if not len(s):
        return {}
    out = {}
    Lm = losses(s["y_bp"], s["model"], s["pipconv"])["mse_log"]
    for k in ("atr", "sh20"):
        d = pd.Series(losses(s["y_bp"], s[k], s["pipconv"])["mse_log"] - Lm, index=s.index)
        w = d.groupby(s["target"].values).mean().sort_index()
        out[k] = {"mean_diff": float(w.mean()), "hac_t_lag24": nw_t(w.values, 24), "n_hours": int(len(w))}
    return out


def _primary(s):  # score.py primary(), with the confirmation readings of prereg section 8 (no postponement)
    b = _block(s)
    if not b["n"]:
        return None
    best = min(("atr", "sh20"), key=lambda k: b[k]["mse_log"])
    d = _dm(s)[best]
    t = d["hac_t_lag24"]
    if b["model"]["mse_log"] >= b[best]["mse_log"]:
        reading = "FAIL"
    elif t is not None and np.isfinite(t) and t > 1.96:
        reading = "PASS"
    else:
        reading = "INDETERMINATE"
    return {"best_free_baseline": best, "model_mse_log": b["model"]["mse_log"], "baseline_mse_log": b[best]["mse_log"],
            "mse_ratio": b["model"]["mse_log"] / b[best]["mse_log"], "hac_t": t, "hours": b["hours"], "reading": reading,
            "label": f"UNDERPOWERED (n < {MIN_HOURS})" if b["hours"] < MIN_HOURS else ""}


def compute_reading(fc_records, rz_records, now=None):
    """The fixed reading. Refused for any sealed-week hour before 2026-12-14 00:00 UTC."""
    now = utcnow() if now is None else now
    hours = {r["target_hour_utc"] for r in fc_records} | {r["target_hour_utc"] for r in rz_records}
    sealed = [h for h in hours if SEALED[0] <= dt.datetime.strptime(h, "%Y-%m-%dT%H:%M:%SZ") < SEALED[1]]
    if sealed and now < READ_NOT_BEFORE:
        raise SealedWindowRefusal(f"refused: scoring {len(sealed)} sealed-week hours before {iso(READ_NOT_BEFORE)}")
    df = build_rows(fc_records, rz_records)
    out = {"targets": int(df["target"].nunique()) if len(df) else 0}
    if not len(df):
        out["reading"] = "NOT READ (data unavailable: no forecast records)"
        return out
    ok = (df["valid"] == 1) & df["status"].eq("ok") & df[["model", "atr", "sh20", "y_bp", "pipconv"]].notna().all(axis=1)
    sc = df[ok].copy()
    out["pair_hours_forecast_ok"] = int(df["status"].eq("ok").sum())
    out["pair_hours_valid"] = int((df["valid"] == 1).sum())
    out["hours_scored"] = int(sc["target"].nunique())
    out["pair_hours_scored"] = int(len(sc))
    out["features_lag_hours_counts"] = {str(k): int(v) for k, v in df["lag"].value_counts(dropna=False).sort_index().items()}
    prim = _primary(sc)
    if prim is None:
        out["reading"] = "NOT READ (data unavailable: no scored pair-hour)"
        return out
    out["primary"] = prim
    out["reading"] = prim["reading"]
    out["label"] = prim["label"]
    out["secondary"] = {"all_hours": _block(sc), "dm_pooled_mse_log": _dm(sc),
                        "release_hours": _block(sc[sc["own_event"] == 1]),
                        "release_next_hours": _block(sc[sc["own_event_next"] == 1]),
                        "per_pair": {p: _block(sc[sc["pair"] == p]) for p in MAJORS}}
    return out


def _clean(o):
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


# ------------------------------------------------------------------------------------------------ selftest
def _leaves(o, path=""):
    if isinstance(o, dict):
        for k in sorted(o):
            yield from _leaves(o[k], f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, o


def _compare(ref, got):
    """Exact comparison after a JSON round trip. Returns (n_leaves_compared, [mismatch descriptions without values])."""
    ref = json.loads(_live.canon(ref))
    got = json.loads(_live.canon(got))
    a, b = dict(_leaves(ref)), dict(_leaves(got))
    bad = []
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            bad.append(f"{k}: present only in {'reference' if k in a else 'replay'}")
        elif isinstance(a[k], float) and isinstance(b[k], float) and np.isnan(a[k]) and np.isnan(b[k]):
            continue
        elif a[k] != b[k] or type(a[k]) is not type(b[k]):
            if isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)) and a[k]:
                bad.append(f"{k}: differs (relative difference {abs(b[k] - a[k]) / abs(a[k]):.3e})")
            else:
                bad.append(f"{k}: differs")
    return len(a), bad


def selftest(evidence=None):
    bad = frozen_check()
    if bad:
        log(f"REFUSED: frozen files differ from their pins: {sorted(bad)}")
        return 2
    GUARD["seen_only"] = True
    recs = {r["hash"]: r for r in _live.read_jsonl(_live.WARMUP)}
    ref, ref2 = recs[SELFTEST_REF_HASH], recs[SELFTEST_REF2_HASH]
    assert ref["target_hour_utc"] == iso(SELFTEST_TARGET) and ref["asof_utc"] == iso(SELFTEST_ASOF)
    assert SELFTEST_ASOF == SELFTEST_TARGET - REPLAY_LEAD
    f = new_fetcher()
    t0 = time.time()
    log(f"selftest: replaying target {iso(SELFTEST_TARGET)} at as-of {iso(SELFTEST_ASOF)} (cache {CACHE})")
    res = _live.make_forecasts(f, SELFTEST_TARGET, SELFTEST_ASOF, log=log)
    res["realized_check"] = {p: _live.realized_hour(f, p, SELFTEST_TARGET) for p in MAJORS}
    got = {"target_hour_utc": iso(SELFTEST_TARGET), "asof_utc": iso(SELFTEST_ASOF), **_live.frozen_hashes(), **res}
    keys = ["target_hour_utc", "asof_utc", "coefficients_sha256", "events_sha256", "pairs", "events", "store_hour",
            "inputs_until_utc", "realized_check"]
    n, mism = _compare({k: ref[k] for k in keys}, {k: got[k] for k in keys})
    keys2 = [k for k in keys if k != "realized_check"]
    n2, mism2 = _compare({k: ref2[k] for k in keys2}, {k: got[k] for k in keys2})
    spans = [file_span(r) for r in ACCESSED]
    ev = {
        "test": "pre-read self-test on already-seen data (CONFIRMATION_PREREG.md section 10)",
        "harness": "confirm/replay_sealed.py", "harness_sha256": harness_sha256(),
        "replayed": {"target_hour_utc": iso(SELFTEST_TARGET), "now_utc": iso(SELFTEST_ASOF)},
        "reference": {"file": "log/warmup.jsonl", "record_hash": SELFTEST_REF_HASH,
                      "fields": keys, "leaves_compared": n, "mismatches": mism},
        "reference_2": {"file": "log/warmup.jsonl", "record_hash": SELFTEST_REF2_HASH,
                        "fields": keys2, "leaves_compared": n2, "mismatches": mism2},
        "exact_match": not mism and not mism2,
        "files_accessed": len(ACCESSED),
        "latest_file_end_utc": iso(max(b for _, b in spans)) if spans else None,
        "any_file_overlaps_sealed_week": any(a < SEALED[1] and b > SEALED[0] for a, b in spans),
        "network_requests": f.n_requests, "http_429": f.n_429, "seconds": round(time.time() - t0, 1),
        "run_utc": iso(utcnow()), "frozen_sha256": FROZEN,
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
    }
    if evidence:
        with open(evidence, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(ev, fh, indent=1)
            fh.write("\n")
    print(json.dumps({k: ev[k] for k in ("exact_match", "files_accessed", "latest_file_end_utc",
                                         "any_file_overlaps_sealed_week", "network_requests")}))
    print(f"reference {SELFTEST_REF_HASH[:12]}: {n} leaves compared, {len(mism)} mismatches")
    print(f"reference {SELFTEST_REF2_HASH[:12]}: {n2} leaves compared, {len(mism2)} mismatches")
    for m in mism + mism2:
        print("  MISMATCH", m)
    return 0 if ev["exact_match"] else 5


# ------------------------------------------------------------------------------------------------ read
def _refuse(msg):
    log(f"REFUSED: {msg}")
    return 2


def read():
    now = utcnow()
    if now < READ_NOT_BEFORE:                     # G3, before anything else (no file, no network)
        return _refuse(f"the sealed week may not be read before {iso(READ_NOT_BEFORE)} (local clock {iso(now)})")
    if os.path.exists(READING_OUT):
        return _refuse(f"a reading already exists ({READING_OUT}); the original reading stands (prereg section 10)")
    bad = frozen_check()
    if bad:
        return _refuse(f"frozen files differ from their pins: {sorted(bad)}")
    hs = harness_sha256()
    pinned = ""
    if os.path.exists(PREREG):
        with open(PREREG, encoding="utf-8") as fh:
            pinned = fh.read()
    if hs not in pinned:
        return _refuse(f"this harness (sha256 {hs}) is not the one pinned in CONFIRMATION_PREREG.md")
    srv = server_utc()
    if srv is None or srv < READ_NOT_BEFORE:
        return _refuse(f"server clock check failed (HTTP Date = {iso(srv) if srv else 'unreadable'})")
    os.makedirs(OUT, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return _refuse(f"lock {LOCK} exists: another read may be running. Remove it only after checking that no "
                       "read process is alive.")
    try:
        os.write(fd, f"pid {os.getpid()} started {iso(now)}\n".encode())
        os.close(fd)
        return _read_locked(hs)
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


def _read_locked(hs):
    for path in (FC_OUT, RZ_OUT):
        try:
            recs = _live.read_jsonl(path)
            ok, at = _live.verify_chain(path)
        except _live.LogCorrupt as e:
            log(f"LOG CORRUPT, nothing written: {e}")
            return 3
        if not ok:
            log(f"LOG CORRUPT, nothing written: {path} chain broken at record {at}")
            return 3
        if any(r.get("harness_sha256") != hs for r in recs):
            return _refuse(f"{path} holds records written by another harness version")
    targets = sealed_targets()
    assert len(targets) == N_TARGETS, len(targets)
    if utcnow() >= DATA_DEADLINE:
        return _not_read(hs, "replay not finished by 2027-01-11")
    f = new_fetcher()
    waits = [60, 120, 300, 600, 900, 1800]

    def with_retry(fn, what):
        for i in range(len(waits) + 1):
            try:
                return fn()
            except ReplayFetchAbort as e:
                if i == len(waits):
                    log(f"{what}: fetch failed after {i + 1} tries ({e}); stopping. A rerun resumes.")
                    raise
                log(f"{what}: fetch failed ({e}); retry in {waits[i]} s")
                time.sleep(waits[i])

    # phase A: frozen forecasts at the live timing
    done = {r["target_hour_utc"] for r in _live.read_jsonl(FC_OUT)}
    for i, T in enumerate(targets, 1):
        if iso(T) in done:
            continue
        now_r = T - REPLAY_LEAD
        n0, q0 = f.n_requests, f.n_429
        try:
            res = with_retry(lambda: _live.make_forecasts(f, T, now_r, log=log), f"forecast {i}/{len(targets)}")
        except ReplayFetchAbort:
            return 4
        _live.append_chained(FC_OUT, {"mode": "sealed-replay", "target_hour_utc": iso(T), "replay_now_utc": iso(now_r),
                                      "run_utc": iso(utcnow()), **_live.frozen_hashes(), "harness_sha256": hs,
                                      "requests": f.n_requests - n0, "http_429": f.n_429 - q0, **res})
        log(f"forecast {i}/{len(targets)} logged (requests so far {f.n_requests})")
    # phase B: realised ranges with the frozen realized_hour (whole hour missing if any pair's file is missing, as
    # score.py collect_realized)
    done = {r["target_hour_utc"] for r in _live.read_jsonl(RZ_OUT)}
    for i, T in enumerate(targets, 1):
        if iso(T) in done:
            continue

        def one_hour():
            pairs = {}
            for p in MAJORS:
                try:
                    pairs[p] = _live.realized_hour(f, p, T)
                except _dk.NotPublished:
                    return None
            return pairs
        try:
            pairs = with_retry(one_hour, f"realised {i}/{len(targets)}")
        except ReplayFetchAbort:
            return 4
        rec = {"target_hour_utc": iso(T), "fetched_utc": iso(utcnow()), "harness_sha256": hs,
               "source": "Dukascopy BID ticks (hourly file)"}
        rec.update({"status": "missing", "pairs": {}} if pairs is None else {"status": "ok", "pairs": pairs})
        _live.append_chained(RZ_OUT, rec)
        log(f"realised {i}/{len(targets)} logged")
    if utcnow() >= DATA_DEADLINE:
        return _not_read(hs, "replay not finished by 2027-01-11")
    # phase C: the reading, once
    fc, rz = _live.read_jsonl(FC_OUT), _live.read_jsonl(RZ_OUT)
    out = compute_reading(fc, rz)
    out = _clean({"computed_utc": iso(utcnow()), "harness_sha256": hs, "frozen_sha256": FROZEN,
                  "forecasts_chain_tip": fc[-1]["hash"], "realized_chain_tip": rz[-1]["hash"],
                  "network_requests": f.n_requests, **out})
    with open(READING_OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, allow_nan=False)
        fh.write("\n")
    print(json.dumps(out, indent=1))
    return 0


def _not_read(hs, why):
    out = {"computed_utc": iso(utcnow()), "harness_sha256": hs, "reading": f"NOT READ (data unavailable: {why})"}
    with open(READING_OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print(json.dumps(out))
    return 0


def status():
    n_fc = len(_live.read_jsonl(FC_OUT))
    n_rz = len(_live.read_jsonl(RZ_OUT))
    print(json.dumps({"targets": N_TARGETS, "forecast_records": n_fc, "realized_records": n_rz,
                      "reading_exists": os.path.exists(READING_OUT), "lock_exists": os.path.exists(LOCK),
                      "read_not_before_utc": iso(READ_NOT_BEFORE), "clock_utc": iso(utcnow()),
                      "harness_sha256": harness_sha256(), "frozen_files_ok": not frozen_check()}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["targets", "selftest", "read", "status"])
    ap.add_argument("--evidence", default=None, help="selftest: write the evidence JSON here")
    a = ap.parse_args(argv)
    if a.mode == "targets":
        ts = sealed_targets()
        for t in ts:
            print(iso(t), "store", utc_to_store(t).strftime("%a %Y-%m-%d %H:%M"))
        print(f"{len(ts)} target hours")
        return 0 if len(ts) == N_TARGETS else 1
    if a.mode == "selftest":
        return selftest(a.evidence)
    if a.mode == "read":
        return read()
    return status()


if __name__ == "__main__":
    sys.exit(main())
