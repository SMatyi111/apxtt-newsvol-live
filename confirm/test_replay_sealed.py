"""Offline tests of confirm/replay_sealed.py. No network, no sealed-week data: synthetic numbers and empty placeholder
files only. The network self-test on already-seen data is `python confirm/replay_sealed.py selftest`.

Run: python confirm/test_replay_sealed.py      (or: python -m pytest confirm/test_replay_sealed.py)
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import replay_sealed as R  # noqa: E402  (installs the guard)
from newsvol import dukascopy as dk  # noqa: E402
from newsvol import live  # noqa: E402
from newsvol.features import G8, MAJORS, utc_to_store  # noqa: E402

D = dt.datetime


class NoNetwork:
    """Replace the raw HTTP call with one that fails and counts. Any count > 0 means a test tried the network."""

    def __enter__(self):
        self.calls = []
        self._orig = dk.Fetcher._get
        calls = self.calls

        def _get(fetcher, rel):
            calls.append(rel)
            raise OSError(f"network use in an offline test: {rel}")
        dk.Fetcher._get = _get
        return self

    def __exit__(self, *exc):
        dk.Fetcher._get = self._orig
        return False


def _tmp():
    return tempfile.mkdtemp(prefix="replay_test_")


def _plant(cache, rel):
    """Empty placeholder file in the cache under the fetcher's naming (decodes to zero bars)."""
    open(os.path.join(cache, rel.replace("/", "_")), "wb").close()


def _day_rel(p, d):
    return f"{p}/{d.year:04d}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"


def _hour_rel(p, h):
    return f"{p}/{h.year:04d}/{h.month - 1:02d}/{h.day:02d}/{h.hour:02d}h_ticks.bi5"


def _before_read_date():
    if R.utcnow() >= R.READ_NOT_BEFORE:
        raise unittest.SkipTest("after 2026-12-14 the guard allows the sealed week by design")


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except BaseException as e:  # noqa: BLE001
        raise AssertionError(f"expected {exc.__name__}, got {type(e).__name__}: {e}") from e
    raise AssertionError(f"expected {exc.__name__}, nothing was raised")


# ------------------------------------------------------------------------------------------------ calendar
def test_targets_are_the_123_store_week_hours():
    ts = R.sealed_targets()
    assert len(ts) == R.N_TARGETS == 123
    assert ts[0] == D(2026, 10, 11, 21) and ts[-1] == D(2026, 10, 18, 23)
    assert sum(1 for t in ts if t < D(2026, 10, 16, 21)) == 120
    assert [t for t in ts if t >= D(2026, 10, 16, 21)] == [D(2026, 10, 18, 21), D(2026, 10, 18, 22), D(2026, 10, 18, 23)]
    assert all(R.SEALED[0] <= t < R.SEALED[1] and utc_to_store(t).weekday() <= 4 for t in ts)


def test_frozen_files_match_pins():
    assert R.frozen_check() == {}


def test_prereg_pins_this_harness():
    if not os.path.exists(R.PREREG):
        raise unittest.SkipTest("CONFIRMATION_PREREG.md not written yet")
    with open(R.PREREG, encoding="utf-8") as fh:
        assert R.harness_sha256() in fh.read()


def test_selftest_reference_records_exist():
    ok, _ = live.verify_chain(live.WARMUP)
    assert ok
    recs = {r["hash"]: r for r in live.read_jsonl(live.WARMUP)}
    for h in (R.SELFTEST_REF_HASH, R.SELFTEST_REF2_HASH):
        assert recs[h]["target_hour_utc"] == "2026-10-07T14:00:00Z" and recs[h]["asof_utc"] == "2026-10-07T13:35:00Z"
    assert R.SELFTEST_ASOF == R.SELFTEST_TARGET - R.REPLAY_LEAD


# ------------------------------------------------------------------------------------------------ guard
def test_guard_is_installed_on_the_class_make_forecasts_uses():
    assert dk.Fetcher._cached is R._guarded_cached
    assert live.Fetcher is dk.Fetcher


def test_check_rel_rule():
    sealed_day = _day_rel("EURUSD", D(2026, 10, 12))
    _raises(R.SealedWindowRefusal, lambda: R.check_rel(sealed_day, now=D(2026, 12, 13, 23, 59, 59), seen_only=False))
    R.check_rel(sealed_day, now=D(2026, 12, 14), seen_only=False)            # allowed from the read date on
    _raises(R.SealedWindowRefusal, lambda: R.check_rel(sealed_day, now=D(2027, 6, 1), seen_only=True))
    R.check_rel(_day_rel("EURUSD", D(2026, 10, 9)), now=D(2026, 11, 10), seen_only=True)
    R.check_rel(_hour_rel("EURUSD", D(2026, 10, 9, 23)), now=D(2026, 11, 10), seen_only=True)
    _raises(R.SealedWindowRefusal, lambda: R.check_rel(_hour_rel("EURUSD", D(2026, 10, 10, 0)), now=D(2027, 1, 1), seen_only=True))
    R.check_rel(_hour_rel("EURUSD", D(2026, 10, 19, 0)), now=D(2026, 11, 10), seen_only=False)
    _raises(R.SealedWindowRefusal, lambda: R.check_rel("EURUSD/2026/09/12/whatever.bi5", now=D(2027, 1, 1), seen_only=False))
    _raises(R.SealedWindowRefusal, lambda: R.check_rel("../EURUSD/2026/09/12/BID_candles_min_1.bi5", now=D(2027, 1, 1), seen_only=False))


def test_sealed_files_refused_from_network_and_cache():
    _before_read_date()
    cache = _tmp()
    try:
        f = dk.Fetcher(cache, min_gap=0)
        cases = [("day", D(2026, 10, 10)), ("day", D(2026, 10, 12)), ("day", D(2026, 10, 18)),
                 ("hour", D(2026, 10, 10, 0)), ("hour", D(2026, 10, 11, 21)), ("hour", D(2026, 10, 18, 23))]
        with NoNetwork() as nn:
            for kind, t in cases:
                for planted in (False, True):
                    rel = _day_rel("EURUSD", t) if kind == "day" else _hour_rel("EURUSD", t)
                    if planted:
                        _plant(cache, rel)   # a sealed file already in the cache is refused as well
                    call = (lambda: f.day_candles("EURUSD", t.date(), now_utc=D(2026, 10, 19))) if kind == "day" \
                        else (lambda: f.hour_ticks_m1("EURUSD", t))
                    _raises(R.SealedWindowRefusal, call)
        assert nn.calls == []
        assert f.n_requests == 0
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def test_seen_files_pass_the_guard():
    cache = _tmp()
    try:
        f = dk.Fetcher(cache, min_gap=0)
        with NoNetwork() as nn:
            for rel, call in ((_day_rel("EURUSD", D(2026, 10, 9)), lambda: f.day_candles("EURUSD", D(2026, 10, 9).date(), now_utc=D(2026, 10, 19))),
                              (_hour_rel("EURUSD", D(2026, 10, 9, 23)), lambda: f.hour_ticks_m1("EURUSD", D(2026, 10, 9, 23))),
                              (_hour_rel("EURUSD", D(2026, 10, 19, 0)), lambda: f.hour_ticks_m1("EURUSD", D(2026, 10, 19, 0)))):
                _plant(cache, rel)
                assert len(call()) == 0
        assert nn.calls == []
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def test_refusal_is_not_swallowed_by_the_frozen_loader():
    """load_m1 catches `Exception` and would silently end the data; the refusal must stop it instead."""
    _before_read_date()
    cache = _tmp()
    try:
        _plant(cache, _day_rel("EURUSD", D(2026, 10, 9)))
        with NoNetwork() as nn:
            _raises(R.SealedWindowRefusal, lambda: live.load_m1(dk.Fetcher(cache, min_gap=0), "EURUSD", D(2026, 10, 9).date(),
                                                                D(2026, 10, 12, 10, 35), hard_end=D(2026, 10, 12, 11)))
        assert nn.calls == []
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def test_refusal_propagates_through_make_forecasts_threads():
    _before_read_date()
    cache = _tmp()
    try:
        T = D(2026, 10, 18, 23)
        for p in MAJORS:   # majors look back 35 days: give them empty pre-window days, so the first real access is sealed
            d = (T - dt.timedelta(days=live.OWN_DAYS)).date()
            while d < R.SEALED[0].date():
                _plant(cache, _day_rel(p, d))
                d += dt.timedelta(days=1)
        assert len(G8) == 28
        with NoNetwork() as nn:
            _raises(R.SealedWindowRefusal, lambda: live.make_forecasts(dk.Fetcher(cache, min_gap=0), T, T - R.REPLAY_LEAD,
                                                                       log=lambda *a: None))
        assert nn.calls == []
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def test_fetch_failure_aborts_instead_of_truncating():
    cache = _tmp()
    try:
        with NoNetwork() as nn:
            f = dk.Fetcher(cache, min_gap=0, waits=())
            _raises(R.ReplayFetchAbort, lambda: live.load_m1(f, "EURUSD", D(2026, 9, 1).date(), D(2026, 9, 2, 10, 35),
                                                             hard_end=D(2026, 9, 2, 11)))
        assert len(nn.calls) == 1   # one (simulated) request, then the abort; no truncated series returned
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def test_read_refused_before_read_date_without_files_or_network():
    _before_read_date()
    existed = os.path.exists(R.OUT)
    with NoNetwork() as nn:
        assert R.main(["read"]) == 2
    assert nn.calls == []
    assert os.path.exists(R.OUT) == existed


def test_reading_refuses_sealed_hours_before_read_date():
    fc, rz = _synthetic(np.random.default_rng(1), [D(2026, 10, 12, 10)], model_noise=0.3)
    _raises(R.SealedWindowRefusal, lambda: R.compute_reading(fc, rz, now=D(2026, 12, 13, 23)))


# ------------------------------------------------------------------------------------------------ reading = score.py
def _synthetic(rng, hours, model_noise, base_noise=(0.5, 0.45)):
    """Synthetic forecast/realised records in the live record layout. Not market data."""
    fc, rz = [], []
    for i, T in enumerate(hours):
        t = T.strftime("%Y-%m-%dT%H:%M:%SZ")
        pf, pr = {}, {}
        for j, p in enumerate(MAJORS):
            y = float(np.exp(rng.normal(2.5, 0.5)))
            rec = {"status": "ok", "features_lag_hours": 2, "own_event_hour": int(i % 17 == 0),
                   "own_event_next_hour": int(i % 17 == 1),
                   "f_model_bp": float(y * np.exp(rng.normal(0, model_noise))),
                   "f_atr_bp": float(y * np.exp(rng.normal(0.1, base_noise[0]))),
                   "f_sh20_bp": float(y * np.exp(rng.normal(-0.05, base_noise[1])))}
            if (i * 7 + j) % 29 == 0:
                rec = {"status": "no_forecast_insufficient_data"}
            if (i * 7 + j) % 31 == 0:
                rec["f_sh20_bp"] = None
            pf[p] = rec
            pr[p] = {"valid": int((i * 7 + j) % 23 != 0), "range_bp": round(y, 6), "pipconv": 1.0 + 0.1 * j}
        fc.append({"mode": "live", "target_hour_utc": t, "pairs": pf, "events": []})
        rz.append({"target_hour_utc": t, "status": "ok", "pairs": pr})
    return fc, rz


def _fx_hours(start, n):
    out, t = [], start
    while len(out) < n:
        if utc_to_store(t).weekday() <= 4:
            out.append(t)
        t += dt.timedelta(hours=1)
    return out


def test_reading_equals_score_py_primary_on_synthetic_data():
    import score
    tmp = _tmp()
    saved = {k: getattr(score, k) for k in ("FORECASTS", "REALIZED", "RECEIPTS", "SCOREBOARD")}
    try:
        hours = _fx_hours(D(2031, 3, 3), 150)
        fc, rz = _synthetic(np.random.default_rng(7), hours, model_noise=0.42)
        score.FORECASTS, score.REALIZED = os.path.join(tmp, "f.jsonl"), os.path.join(tmp, "r.jsonl")
        score.RECEIPTS, score.SCOREBOARD = os.path.join(tmp, "rc.jsonl"), os.path.join(tmp, "sb.json")
        for r in fc:
            live.append_chained(score.FORECASTS, r)
            T = dt.datetime.strptime(r["target_hour_utc"], "%Y-%m-%dT%H:%M:%SZ")
            live.append_chained(score.RECEIPTS, {"target_hour_utc": r["target_hour_utc"],
                                                 "pushed_utc": (T - dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        for r in rz:
            live.append_chained(score.REALIZED, r)
        board = score.build_scoreboard(D(2031, 6, 1))
        mine = R.compute_reading(live.read_jsonl(score.FORECASTS), live.read_jsonl(score.REALIZED), now=D(2031, 6, 1))
        ref = board["primary_running"]
        for k in ("best_free_baseline", "model_mse_log", "baseline_mse_log", "mse_ratio", "hac_t", "hours"):
            assert mine["primary"][k] == ref[k], (k, mine["primary"][k], ref[k])
        assert mine["hours_scored"] == board["hours_scored"] and mine["pair_hours_scored"] == board["pair_hours_scored"]
        assert R._clean(mine["secondary"]["all_hours"]) == board["all_hours"]
        assert R._clean(mine["secondary"]["dm_pooled_mse_log"]) == board["dm_pooled_mse_log"]
        assert R._clean(mine["secondary"]["release_hours"]) == board["release_hours"]
        assert R._clean(mine["secondary"]["release_next_hours"]) == board["release_next_hours"]
        assert R._clean(mine["secondary"]["per_pair"]) == board["per_pair"]
        assert ref["reading_if_read_now"] == "not enough hours yet"           # live rule: postpone below 600 hours
        assert mine["reading"] in ("PASS", "FAIL", "INDETERMINATE")             # confirmation rule: read once
        assert mine["label"] == "UNDERPOWERED (n < 600)"
    finally:
        for k, v in saved.items():
            setattr(score, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


def test_reading_labels():
    hours = _fx_hours(D(2031, 3, 3), 120)
    good = R.compute_reading(*_synthetic(np.random.default_rng(3), hours, model_noise=0.1), now=D(2031, 6, 1))
    assert good["reading"] == "PASS" and good["primary"]["hac_t"] > 1.96
    bad = R.compute_reading(*_synthetic(np.random.default_rng(4), hours, model_noise=1.0), now=D(2031, 6, 1))
    assert bad["reading"] == "FAIL" and bad["primary"]["model_mse_log"] >= bad["primary"]["baseline_mse_log"]
    few = R.compute_reading(*_synthetic(np.random.default_rng(5), hours[:8], model_noise=0.1), now=D(2031, 6, 1))
    assert few["primary"]["hac_t"] != few["primary"]["hac_t"]                     # NaN: fewer than 10 hours
    assert few["reading"] in ("INDETERMINATE", "FAIL")
    if few["primary"]["model_mse_log"] < few["primary"]["baseline_mse_log"]:
        assert few["reading"] == "INDETERMINATE"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        try:
            f()
            print("PASS", n)
        except unittest.SkipTest as e:
            print("SKIP", n, "-", e)
        except BaseException as e:  # noqa: BLE001
            failed += 1
            print("FAIL", n, "-", type(e).__name__, e)
    print(f"{len(tests) - failed}/{len(tests)} passed or skipped, {failed} failed")
    sys.exit(1 if failed else 0)
