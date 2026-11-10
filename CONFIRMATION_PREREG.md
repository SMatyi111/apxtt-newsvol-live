# Confirmation preregistration: the sealed week 2026-10-10 00:00 .. 2026-10-18 23:59 UTC

**Status: BINDING.** Approved by the owner on 2026-11-10 (section 12). This file is committed to the public repository
with the annotated tag `confirm-v1`, before the read date of 2026-12-14; the tagged commit is its public timestamp.
Its sha256 is also pinned in the owner's embargo registry. Written 2026-11-10 by Claude (an AI assistant) to carry out
the owner's decisions of 2026-11-10, "Read with the 12-14 read (Recommended)" and "Exempt + commit publicly
(Recommended)".

**Nothing in the sealed window has been fetched, decoded or computed** by the author of this file, by the replay
harness or by its tests, up to the commit tagged `confirm-v1`. The only contact with window data: two HTTP HEAD
requests, which return headers and no file body. Only the status code was kept (section 4). The harness self-test
(section 10) read only files that end on or before 2026-10-10 00:00 UTC; its evidence file records this.

Tags used below:
- **[COPY §n]**: copied from `PREREGISTRATION.md` (tag `prereg-v1`), section n.
- **[ADAPT]**: changed only because this week is replayed after the fact, not forecast live. The reason is given.
- **[NEW]**: a rule the live prereg does not have. Approved by the owner on 2026-11-10 (section 12, C4).

---

## 0. Where this comes from
- **Live prereg §7 (decision A, 2026-10-17):** "The window 2026-10-10 00:00 .. 2026-10-18 23:59 UTC is a sealed
  one-shot confirmation window (owner decision A, 2026-10-17). No forecast is made for, no outcome is fetched for, and
  nothing is printed about any hour in it."
- **Embargo registry** (`apxtt-newsvol-live`, SEALED row 2026-10-10..10-19): "one-shot confirmation window of the
  frozen model (coefficients sha256 21663b2a...). Never a target of the live log; read once only under its own prereg."
  This file is that prereg.
- **Owner decision 2026-11-10:** "Read with the 12-14 read (Recommended)". First write a short confirmation prereg
  (frozen model, same metrics, readings fixed in advance). Then read the week **once**, together with the formal
  live-log read on 2026-12-14.
- **Owner decision 2026-11-10:** "Exempt + commit publicly (Recommended)". Confirm E1 and extend it to the sealed week;
  commit this prereg to the public repo with tag `confirm-v1`; write the replay harness; read once with the 12-14 read
  (section 12).

## 1. Question [COPY §1, window changed]
Does the frozen model forecast the next hour's high-low range of the 7 major FX pairs better than the best of two
free tools? The tools are ATR(14) on H1 and the 20-day average range of the same hour. The test data are the sealed
week, which no fit, calibration, feed intercept or forecast has used.

Null: the model's mean squared log error is not lower than the best free tool's.

## 2. Frozen model, by hash [COPY §3]
| file | sha256 (checked 2026-11-10 with `sha256sum`) |
|---|---|
| `model/coefficients.csv` | `21663b2aedcd6ecec87a6d13f482b4c4d87adb2ae261d1a9eb035a5c8d18ced4` |
| `model/events_utc.csv` | `da1da082e25f011829ac4320144098b84dc82e891328ff31be8acef7bbb65e1b` |
| `PREREGISTRATION.md` | `bffc98dff566d29f3211fb23bacc632d0a33f9e198cac5516b1a3fee49b6ffa4` (same as the registry pin) |

The forecasters are the same three as the live log: FULL, with NOF only if the market factor cannot be computed;
ATR(14) H1 x exp(k_atr + d_atr); same-hour 20-day x exp(k_sh20 + d_sh20). The model gets its feed intercept d_model.
All of them come from the frozen coefficient file. Nothing is refitted.

**Frozen code.** The replay uses the functions as of commit `8b092db`. On 2026-11-10 that commit was still the newest
change on `origin/main` for `newsvol/`, `model/`, `score.py`, `forecast.py`, `AMENDMENTS.md` and
`PREREGISTRATION.md` (checked with `gh api .../commits?path=...`). The forecasting and realised-range code has not
changed since `prereg-v1`. `git diff prereg-v1 HEAD` touches only three things: the log-safety code in
`newsvol/live.py` (A1), the A0 freshness gate in `forecast.py`, and A1 in `score.py`. It does not touch
`make_forecasts` or `realized_hour`. sha256 of the blobs at `8b092db`:

| file | sha256 |
|---|---|
| `newsvol/live.py` (`make_forecasts`, `realized_hour`, `load_m1`) | `5845e419dcc7454ebd9d94c1fb3f5257b0dfd35191017619bc852eb21617d9cb` |
| `newsvol/features.py` | `44ed121ae8b93e92b460cc6053e7a62659011088c9540b2eb420ed93b0ff76e6` |
| `newsvol/model.py` | `5931efdd4c29ebb719bf70d963148bedad86a45d559b13f2738d2c59bf4889d9` |
| `newsvol/events.py` | `85b63e8e9d3eae8bfd23d46fd1ee437d1f0313da6eafd1067c2bc382c947e8c3` |
| `newsvol/metrics.py` (`losses`, `nw_t`) | `0368b928dd24d16244957a42ef954fe8c1059166769ff02dca8e9295ca6d17df` |
| `newsvol/dukascopy.py` | `0c04cb73d28250437c18d757752d7546019f8d3a59e7b508989bc000b294f623` |
| `score.py` (`primary()` logic copied for the reading) | `2ca4536480d089db40b8ad4b58e8438d7fdd210520b46b46503d39340a059424` |

The harness (section 10) checks all ten hashes above before it runs and refuses to run if any differs.

## 3. Hours scored
- **Pairs [COPY §2]:** EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD.
- **Clock [COPY §2]:** the store clock is New York + 7 h. During US daylight time (all of this window) that is UTC+3,
  and store 00:00 = New York 17:00. A target is every UTC hour in the window that falls in the FX week, store clock
  Monday 00:00 to Friday 23:59.
- **Target hours (listed with the frozen `utc_to_store`; no prices used): 123**
  - UTC 2026-10-11 21:00 .. 2026-10-16 20:00 (store Mon 10-12 00:00 .. Fri 10-16 23:00): 120 hours.
  - UTC 2026-10-18 21:00 .. 23:00 (store Mon 10-19 00:00 .. 02:00): 3 hours. The live log starts at 10-19 00:00 UTC,
    so these first three store hours of that week belong to the sealed window.
  - UTC 10-10 00:00 .. 10-11 20:00 and 10-16 21:00 .. 10-18 20:00 are the store weekend. They are not targets.
  - `python confirm/replay_sealed.py targets` prints the list (calendar only); a test checks it.
- **Valid hour [COPY §2], exactly as `realized_hour()`:** the hour needs at least 50 one-minute BID returns, positive
  realised variance, positive range, a previous close, and store Mon-Fri. The first return may use the previous
  hour's last bar. Hours that fail are logged, not scored. *Expectation, UNVERIFIED:* the two Sunday-open hours
  (UTC 10-11 21:00 and 10-18 21:00) probably fail, because the previous close comes only from the previous UTC hour's
  tick file, and FX is closed then. The same code path handles every Sunday open of the live log.
- **Scored pair-hour [COPY §5, minus the timing rule]:** a valid hour, forecast status `ok`, and all three forecasts
  present (`f_model_bp`, `f_atr_bp`, `f_sh20_bp`, plus `pipconv`). The live "on time" condition is replaced by the
  replay timing rule (section 5).
- **Scheduled events in the window** (frozen `events_utc.csv`, schedule only): US jobless claims and US PPI, both at
  2026-10-15 12:30 UTC. So the window has **one** own-event hour for all 7 pairs (12:00 UTC) and one hour-after
  (13:00 UTC). The frozen calendar has no US CPI in October 2026. The macro-event-calendar skill also lists no
  October CPI. Advance retail sales came out on 10-15, but they are not one of the 12 events.

## 4. Data [COPY §2]
- Dukascopy BID: hourly tick files `datafeed.dukascopy.com/datafeed/<PAIR>/<YYYY>/<MM0>/<DD>/<HH>h_ticks.bi5`. The
  frozen loader uses `BID_candles_min_1.bi5` day files for complete past days. Bars built from ticks equal the candle
  bars exactly (README check 5, `calibration/check_ticks.py`; verified on EURUSD and USDJPY, 5 hours each). The target
  is `range_bp = 1e4 ln(max BID / min BID)` of the UTC hour.
- **Availability check (2026-11-10, status codes only, no body downloaded, nothing decoded):**
  - `HEAD EURUSD/2026/09/12/10h_ticks.bi5`: HTTP 200 (19:51:44Z)
  - `HEAD EURUSD/2026/09/12/BID_candles_min_1.bi5`: HTTP 200 (19:52:09Z)

  (MM0 09 = October.) The files for 2026-10-12 are served. Other pairs and hours were not checked.
- Raw files go to a private cache outside the repo. They are never committed (Dukascopy licence, as in the live log).

## 5. Timing: the replay at the live timing [ADAPT §4]
In the live log the forecast is pushed before the hour, which proves its timing. A replay has no push. Instead, each
target is forecast with the frozen code and the same data cut the live log gets:

- For each target hour T: `make_forecasts(fetcher, T, now = T - 25 min)`. That is a run at minute 35 of the hour
  before, as in `hourly.yml`. `load_m1(..., hard_end = T)` never requests the target hour or later.
- The newest complete hour is T-2h, so `data_until = T-1h` and `features_lag_hours = 2` for every pair. This matches
  A0's freshest-data rule for early runs, and the "lag2" / "Dukascopy, live timing" column of the calibration check
  (README check 3, `calibration/feed_adjust.py`; `newsvol/calib.py` sets D = T - (lag-1) h).
- Every published file exists by now, so lag 2 should hold for every pair-hour. If a gap in the data makes it larger,
  the forecast is still scored as computed, as a live run from minute 45 on would be, and the lag is reported.
- **No receipt / on-time rule:** there is no live push to time. Every target hour is forecast, so no hour is lost
  to operations. The one live difference left: the live code builds the day of the target from hour tick files, and
  sometimes the previous day too. The replay reads the previous day from its day file. By README check 5 the two
  give equal bars.
- Realised range: `realized_hour(fetcher, pair, T)`, unchanged.

## 6. How lookback inputs cross into the window (rule D1) [COPY §7, plus the replay detail]
- Inputs per target: one-minute BID bars of the 7 majors for 35 calendar days back (`OWN_DAYS`), and of the other
  21 G8 pairs for 5 days back (`OTHER_DAYS`), up to T-1h. For the first targets the inputs are wholly SEEN data, from
  2026-09-06 to the last FX hour before the window (Fri 10-09 20:59 UTC). Later targets also use earlier hours of
  the window itself as inputs, as any one-hour-ahead forecaster must. All of this happens inside the single read.
- **Before the read date, nothing in the window is fetched, decoded or computed, not even as an input.** A feature
  such as `c1` is the realised variance of hour T-2, so computing the forecasts early would already open the window.
  Forecasts and outcomes are computed in one run, on or after 2026-12-14.
- **Known D1 leak (accepted, not fixable).** The live forecaster's lookback inputs crossed the window inside the
  GitHub runner (live prereg §7). So the **public** records of the first live hours (from 10-19 00:00 UTC) contain
  sums built from sealed hours: the ATR(14) state, 20-day same-hour means that include 10-12..10-16, the HAR-CJ means,
  and `ref_close`. They do not give the scored hour-by-hour ranges, and the frozen forecasters cannot react to them.
  Rule [NEW]: nobody derives sealed-hour values from those records before the read. The runner's private raw-data
  cache also held window files as inputs. `hourly.yml` deletes cached files older than 40 days.
- Size of the read (estimated with a dry run of the frozen loader's path logic; file names only, no network): about
  **3,815 Dukascopy files** (546 day files and 3,269 hour files). 3,493 of them touch the window and 322 are from
  before 10-10. At the roughly 4 files a minute that live prereg §3 measured from a GitHub runner, that is about
  16 hours, so it runs as one detached, resumable job (section 10).

## 7. Losses and baselines [COPY §3, §5]
- **ATR(14) H1:** Wilder ATR (true range, alpha 1/14) of the hourly bars, last complete hour, in bp of that hour's
  close, x exp(k_atr + d_atr).
- **Same-hour 20-day:** mean range of the same store hour over the previous 20 valid trading days (at least 12),
  x exp(k_sh20 + d_sh20).
- Per scored pair-hour, with y and f the realised and forecast range in bp: **MSE-log** `(ln y - ln f)^2` (primary);
  **QLIKE** `y^2/f^2 - ln(y^2/f^2) - 1`; **MAE in pips** `|f - y| x previous close / 1e4 / pip`; **within +-25%**
  `|f/y - 1| <= 0.25`. Computed by `newsvol.metrics.losses` (hash above).

## 8. Primary test and readings (fixed now) [COPY §6]
- **Best free baseline:** whichever of ATR(14) H1 and same-hour 20-day has the lower pooled MSE-log over the same
  scored pair-hours. It is chosen after the fact, which favours the baselines.
- **Statistic:** for each scored hour, the mean over pairs of `MSE-log(best baseline) - MSE-log(model)`. Then a
  Diebold-Mariano t with a Newey-West HAC variance (Bartlett weights), **lag 24 hours**: `newsvol.metrics.nw_t(w, 24)`,
  aggregated exactly as `score.py` `primary()` / `dm()`.
- **PASS:** the model's pooled MSE-log is lower than the best free baseline's **and** HAC t > 1.96.
- **FAIL:** the model's pooled MSE-log is not lower.
- **INDETERMINATE:** lower, but t <= 1.96, or t undefined (`nw_t` returns NaN with fewer than 10 hours).
- **[ADAPT] Always labelled UNDERPOWERED.** The live prereg wants at least 600 scored hours and postpones a short read
  week by week. This window is fixed at 123 target hours or fewer, so it cannot be postponed into more data. The
  reading is made once and labelled "UNDERPOWERED (n < 600)".
- **Secondary, cannot pass or fail [COPY §6]:** release hour (one hour x 7 pairs, 10-15 12:00 UTC), the hour after
  (13:00 UTC), QLIKE, MAE in pips, within +-25%, per pair, and the model vs the other free tool.
- **[NEW] The live primary test does not change.** The week is a separate reading. It is never pooled with the live
  window 2026-10-19 .. 2026-12-13, and it cannot turn the live reading up or down. (Live prereg header: changes
  "never move the primary test".) Both readings are reported side by side, whatever they show. If they disagree,
  both are reported and there is no tie-break.

## 9. Honest power statement
Basis: published numbers from the SEEN calibration window (README check 3, Dukascopy, live timing, 2026-08-07..10-09,
1,103 pooled hours per `calibration/output/feed_check_dm_pooled.csv`, counts column only). There, the model vs the
same-hour average gave t = 3.9 (MSE ratio about 0.88), and vs ATR t = 13.1. Same-hour was the better free tool
(MSE-log 0.195 vs 0.306), so the binding comparison here is almost certainly the model vs the same-hour average.

Scaling t by sqrt(n / 1,103), with n about 120 scored hours (123 minus the probably invalid Sunday opens). Normal
approximation, same long-run variance as the calibration window:

| if the true effect equals the calibration effect | vs same-hour (binding) | vs ATR |
|---|---|---|
| expected t | 1.29 | 4.32 |
| P(PASS: lower and t > 1.96) | **about 0.25** | about 0.99 |
| P(FAIL: not lower) | **about 0.10** | about 0.00 |
| P(INDETERMINATE) | **about 0.65** | about 0.01 |

- With no true effect: P(PASS) is about 0.025 nominally, P(FAIL) about 0.5, P(INDETERMINATE) about 0.475. So a PASS
  is about 10x more likely under the calibration effect than under no effect, and a FAIL about 5x less likely.
  INDETERMINATE is the most likely outcome either way and says almost nothing (ratio about 1.4).
- 80% power would need an expected t of about 2.8, about 2.2x the calibration effect. That is roughly an MSE ratio of
  0.74 instead of about 0.88, if the per-hour loss-difference variance stays the same.
- The test is generous to the model. With lag 24 on about 120 hours (bandwidth/n of about 0.2), the Newey-West t has
  heavier tails than normal (fixed-b asymptotics). So the copied 1.96 cut gives a false-PASS rate above the nominal
  2.5% one-sided. *How much is UNVERIFIED (from memory: the Kiefer-Vogelsang Bartlett critical value at b = 0.2 is
  around 2.5).* The cut stays 1.96 because the owner asked for the same test.
- It is one week, one regime and one event hour. Monday 10-12 is a US (Columbus Day) and Japanese (Sports Day)
  holiday: FX trades, but liquidity may be thinner. These are calendar facts, not outcome data. The release-hour
  subset (7 pair-hours) is descriptive only.

## 10. Read date and procedure
- **Read on or after 2026-12-14 (UTC), together with the live formal read.** The live read comes from `score.py`
  (`formal_read`, hours < 2026-12-14). Both readings are computed before either is written up. Both go into
  `READ_2026-12-14.md` (live prereg §6), under separate headings, whatever they show.
- **Replay harness [NEW, written, tested and frozen with this file]:**

  | file | sha256 |
  |---|---|
  | `confirm/replay_sealed.py` (the harness) | `d814f8093fd3ea632f66cc1861a326f03eb6fe71f638a88431b615953aa40611` |
  | `confirm/test_replay_sealed.py` (offline tests) | `415f4be9e75dcb69a977a1198abc2127707e2dbe12dde05b569775e12c5a3027` |
  | `confirm/selftest_evidence.json` (pre-read self-test result) | `1df2e5be597ffcb20424be37b354e5a3b685e007c0a26ebe89bc499f5cf96e07` |

  - It calls the frozen `make_forecasts` / `realized_hour` with the timing in section 5 (`now = T - 25 min`), and the
    reading logic of section 8: `score.py` `block()`, `dm()` and `primary()`, copied without the push-receipt rule.
    A test checks on synthetic data that it gives the same numbers as `score.py`.
  - It writes hash-chained records carrying the frozen-file hashes, the harness hash and `features_lag_hours`
    (`confirm/sealed_read/forecasts_sealed.jsonl`, `confirm/sealed_read/realized_sealed.jsonl`), then the reading
    (`confirm/sealed_read/reading_sealed.json`).
  - Before 2026-12-14 00:00 UTC it **refuses** to request any file that overlaps 2026-10-10..10-19, like the hard-end
    asserts in the live code and the date refusal in other studies' `evaluate.py`. The guard sits on the frozen
    fetcher class, so it covers the network and the raw-file cache, and the fetchers that `make_forecasts` creates in
    its threads. The refusal cannot be swallowed by the frozen loader's error handling. `read` refuses to start before
    that date by the local clock and by the HTTP Date header of the data server. It also refuses if a frozen file
    differs from its hash (section 2), if its own sha256 is not the one written here, or if a reading already exists.
    It has no clock override.
  - A fetch failure other than HTTP 404 stops the target and retries it, instead of letting the frozen loader end the
    inputs early (the live workflow retried such hours in a later run, A0). A rerun resumes from the cache and the
    chained records. A file the server does not have (HTTP 404) is handled exactly as the live code handles it.
  - If no pair-hour can be scored, or the replay has not finished by 2027-01-11, it writes NOT READ (data
    unavailable), as the data-failure rule below says.
  - Its sha256 is in the table above, before the read.
  - Pre-read test only on SEEN data: it must reproduce exactly the forecasts in `log/warmup.jsonl` (self-test, as-of
    2026-10-07 13:35, target 14:00 UTC). `python confirm/replay_sealed.py selftest` compares the replay with the
    warm-up record `8899502778f6...` (the newest one, made by the `prereg-v1` code) and with the earlier record
    `4356775e3565...` of the same code path: forecasts, model variant, data coverage of all 28 pairs, event flags,
    and the realised-range path on that SEEN hour. **Result (2026-11-10, `confirm/selftest_evidence.json`): exact
    match.** 0 mismatches in 201 compared values (record `8899502778f6...`) and 0 in 138 (record `4356775e3565...`).
    It read 728 files; the latest ends 2026-10-07 15:00 UTC, and none overlaps the sealed week. Python 3.12.10, numpy
    2.4.4, pandas 2.3.3. The evidence run read everything from the private cache. Earlier runs of the same harness
    filled that cache the same evening; two of them stopped on a network timeout of the data server, which the
    harness turned into an abort (no truncated inputs), as designed. The third finished with the same exact match.
  - Offline tests (`python confirm/test_replay_sealed.py`, no network, synthetic data or empty placeholder files
    only): the 123 target hours; the refusal from the network and from the cache, through `load_m1` and through
    `make_forecasts`' threads; no refusal for SEEN files; `read` refused before the date; scoring refused for sealed
    hours before the date; the reading equals `score.py` on synthetic data; the three reading labels; this file pins
    the harness. 2026-11-10, with this file in place: 15 of 15 passed (as a script and under pytest 8.3.5).
- **One run.** Detached and resumable, with raw files in a private cache outside the repo. Nothing about the window
  is printed until the reading is computed. A rerun is allowed only after a crash that produced no reading. A bug
  found after the reading is reported, and the original reading stands (live prereg §8: hours forecast under a bug
  "are scored as they were logged").
- **[NEW] Data failure:** if Dukascopy cannot serve the files and the replay cannot finish by 2027-01-11 (the live
  prereg's own latest read date), the confirmation is reported as NOT READ (data unavailable).
- After the read: the registry row moves SEALED -> SPENT in the same session, and the files are re-pinned.

## 11. Limits
- This is a replay, not a live test: timing is enforced by code, not proven by a push receipt. Its evidence rests on
  the frozen files, which were hash-published on 2026-10-17, before any byte of this week was read for this model.
- Dukascopy might have revised files since October. Nobody can check that.
- The week is short (section 9). It can support the live result; it cannot replace it.
- It forecasts the size of the move, never its direction. Next hour only. Not financial advice.

## 12. Embargo / R2 note and owner decisions
**Registry check, 2026-11-10** (`registry.py check --features volatility_history,calendar,cross_asset,price_history
--targets range,realized_vol --assets <7 majors> --start 2026-10-10T00:00:00Z --end 2026-10-19T00:00:00Z
--when 2026-12-14T00:00:00Z`):
```
--purpose confirmation
R1 (blocks reading at 2026-12-14): 1
   apxtt-newsvol-live SEALED 2026-10-10 -> 2026-10-19 resolves: never
R2 (window not clean for confirmation): 2
   apxtt-newsvol-live SEALED 2026-10-10 2026-10-19
   fx-vol-managed-carry-2026 PROSPECTIVE 2026-10-13 2028-09-16
--purpose supervised (schema default)
R1 (blocks reading at 2026-12-14): 1
   fx-vol-managed-carry-2026 PROSPECTIVE 2026-10-13 -> 2028-09-16 resolves: 2028-09-15
R2 (window not clean for confirmation): 2
   apxtt-newsvol-live SEALED 2026-10-10 2026-10-19
   fx-vol-managed-carry-2026 PROSPECTIVE 2026-10-13 2028-09-16
```
- The `apxtt-newsvol-live` lines are the window itself (it is SEALED until this read spends it).
- **R1 depends on the purpose label.** `registry/SCHEMA.md` allows only `supervised | representation | both` as
  purposes. `"confirmation"`, used on this window's row, is outside the schema. Under the schema value, and under the
  rule text ("no target outcomes, for evaluation or as training rows, inside an unresolved blocking related window"),
  the carry window **blocks** this read until 2028-09-15. Uncertain cases must fail closed, so it was read as blocked
  unless the owner exempts it. The owner exempted it (C2 below).
- **R2:** 96 of the 123 target hours (from 2026-10-13 00:00 UTC) lie inside the carry study's PROSPECTIVE window.
  Only the 27 hours from 10-11 21:00 to 10-12 23:00 are R2-clean.
- **Why an exemption is reasonable (same reasoning as E1):** fx-vol-managed-carry-2026 logs only frozen daily
  DECISIONS. Its logger computes no return, and its read is on 2028-09-15. Reading 4 trading days of hourly ranges
  cannot change any of its decisions. The live log already publishes hourly ranges for every day since 10-19 under
  E1. Caveat: the carry study's F1 (QLIKE of next-day V0 realised vol) includes those 4 days, so this read does see
  inputs to about 4 of its ~500 forward days.
- **Naming clash:** "E1" in this repo means the exemption vs fx-vol-managed-carry-2026. "E1" in the carry study's own
  prereg (§5) is a different exemption.

**Owner decisions, 2026-11-10.** The owner chose the option "Exempt + commit publicly (Recommended)" (the option's
label, verbatim). As put to the owner, the option means:
- **C1. E1 confirmed for the live log.** Live prereg §7 recorded E1 and said it "is flagged to the owner for
  confirmation". It is now confirmed.
- **C2. E1 extended to this one-shot read** of the sealed week, which overlaps the carry study's PROSPECTIVE window,
  for both R1 and R2. (The alternative put to the owner: the week is not read on 2026-12-14 and stays SEALED, with no
  partial read; the 27 R2-clean hours would give P(PASS) of about 0.09 under the calibration effect.)
- **C3. Commit publicly:** option (a), this file is committed to the public repo as `CONFIRMATION_PREREG.md` with the
  tag `confirm-v1` before 2026-12-14, which gives a public timestamp. The replay harness (section 10) is written,
  tested on SEEN data and hash-pinned before the read.
- **C4. The three [NEW] rules are adopted as part of this approved prereg:** no pooling with the live test (§8), no
  deriving sealed values from the public 10-19 records (§6), and NOT READ if the data cannot be fetched by 2027-01-11
  (§10).
