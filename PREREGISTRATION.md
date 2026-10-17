# Preregistration: live test of the APXTT News Volatility Warning (next-hour FX range forecast)

Written and committed on 2026-10-17, before the first scored hour (2026-10-19 00:00 UTC). The binding commit is tagged
`prereg-v1`. Everything below was fixed before any live outcome existed. Changes go to `AMENDMENTS.md` with a date;
a change made after outcomes exist says so in its first line and never moves the primary test.

## 1. Question
Does the frozen model forecast the next hour's high-low range of 7 major FX pairs better than the best of two free
tools a trader already has (ATR(14) on H1, and the 20-day average range of the same hour), on live data it has never seen?

Null: the model's mean squared log error is not lower than the best free tool's.

## 2. What is forecast
- **Pairs:** EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD.
- **Target:** the high-low range of each UTC hour, from Dukascopy BID prices (hourly tick file
  `datafeed.dukascopy.com/datafeed/<PAIR>/<YYYY>/<MM0>/<DD>/<HH>h_ticks.bi5`): `range_bp = 1e4 * ln(max BID / min BID)`.
  The same ticks give one-minute BID bars (open, high, low, close per minute); minutes without ticks have no bar.
- **Hours:** every UTC hour from 2026-10-19 00:00 on that lies in the FX week (store clock Monday 00:00 to Friday 23:59;
  store clock = New York + 7 h = UTC+3 during US daylight time and UTC+2 otherwise; store 00:00 = New York 17:00).
- **Valid hour (applies to all forecasters alike):** at least 50 one-minute returns between consecutive minute bars
  in the hour (the first one may use the last bar of the previous hour), positive realised variance, positive range,
  and a previous close. Thin hours (holidays, the Sunday open) that fail this are logged but not scored.

## 3. The three forecasters (frozen)
All three forecast `log range_bp` and are converted to pips with the last close available at forecast time.
1. **Model (FULL):** the regression of fx-vol-seasonality-2026 / product_check "FULL" re-fitted on log range:
   hour-of-day (23), weekday (4) and month (11) dummies on the store clock, a linear time counter (capped at its
   2026-10-09 value), HAR-CJ terms from one-minute returns (continuous variation of the last hour / 24 / 120 valid
   hours, last jump size, 24-hour jump frequency and size; Huang-Tauchen jump test at 99.9%), a market factor (mean
   one-minute log realised vol of the other 27 G8 pairs, last hour and 24-hour mean), and 12 scheduled events
   (NFP, US CPI, FOMC, ECB, BoE, US jobless claims, US PPI, ISM manufacturing, BoC, RBA, SNB, BoJ) x (release hour,
   hour after). If the market factor cannot be computed, the NOF variant (same without the factor) is used and
   the record says so.
2. **ATR(14) H1:** Wilder ATR (true range, alpha 1/14) of hourly bars, last complete hour, in bp of that hour's close.
3. **Same-hour 20-day average:** mean range of the same store hour over the previous 20 valid trading days (at least 12).

Each baseline carries one log intercept fitted on the calibration data ("k x ATR"), exactly as in product_check,
so no forecaster is handicapped by a scale it was never given.

**Frozen files** (SHA-256 of the committed bytes; `sha256sum model/*`):
- `model/coefficients.csv` : `21663b2aedcd6ecec87a6d13f482b4c4d87adb2ae261d1a9eb035a5c8d18ced4`
- `model/events_utc.csv` : `da1da082e25f011829ac4320144098b84dc82e891328ff31be8acef7bbb65e1b`

### Calibration (how the frozen numbers were made), and a deviation from the plan
- **Planned:** re-fit everything on Dukascopy one-minute data 2018-06..2023-12. **Not done.** Dukascopy now rate-limits
  its public datafeed (HTTP 429/503, ~4 files per minute from a GitHub runner; bulk history is offered only from a
  requester-pays AWS bucket, which costs money and was not approved). A full re-fit needs ~74,000 day files.
- **Done instead:** the coefficients and baseline intercepts are the production fit of the MT5 product
  (fx-edge-kit/mt5-news-vol, MT5 broker one-minute data, store clock 2018-06-01..2026-10-09; reproduced here by
  `calibration/fit.py`, max coefficient difference < 1e-14). Because the live data come from a different feed
  (Dukascopy), every forecaster gets one per-pair **feed intercept** (`d_model`, `d_atr`, `d_sh20`): its mean log
  error on Dukascopy BID data over the already-seen window 2026-08-07..2026-10-09, with the live timing
  (`calibration/feed_adjust.py`). Same treatment for all three forecasters.
- Sanity checks on already-seen data: README section "Calibration checks" and `calibration/output/`.
- No data on or after 2026-10-10 00:00 UTC was read for calibration.

## 4. Timing (no look-ahead)
- A GitHub Actions job runs at minute ~35 of every hour (`.github/workflows/hourly.yml`) and forecasts the **next**
  UTC hour. It may only use Dukascopy files published before it runs; it never requests any file of the target hour
  or later (enforced in code). In practice the newest complete hour is the one before the current hour, so features
  are one hour older than in the research (each record states `last_complete_hour_utc` and `features_lag_hours`).
  The baselines use exactly the same data cut.
- **On time = pushed before the hour starts.** After pushing the forecast commit, the job appends a receipt with the
  runner's UTC clock (`log/receipts.jsonl`). A forecast whose receipt is at or after the target hour start, or that
  has no receipt, is **late, not scored** (it stays in the log). GitHub also keeps its own push record.
- `log/forecasts.jsonl` and `log/realized.jsonl` are append-only and hash-chained (`prev_hash`, `hash` = SHA-256 of the
  canonical JSON record without `hash`). Each forecast record carries the SHA-256 of both frozen files.
- Realised ranges are added by a later run once the hour's tick file is published; if it is still missing after
  72 hours the hour is written as missing and not scored.

## 5. Scoring
Per scored pair-hour (valid hour, on time, all three forecasts present), with y and f the realised and forecast range in bp:
- **MSE-log** `(ln y - ln f)^2` (primary loss); **QLIKE** `y^2/f^2 - ln(y^2/f^2) - 1`; **MAE in pips**
  `|f - y| * previous close / 1e4 / pip` (pip = 0.01 for JPY pairs, 0.0001 otherwise); **within +-25%** `|f/y - 1| <= 0.25`.
- Subsets: all hours; **release hours** (an own-currency event hour of the 12 events for the pair, e.g. any USD event
  for all 7 pairs, ECB for EURUSD); the hour after a release; per pair.

## 6. Primary test and readings (fixed now)
- **Window of the first formal read:** target hours 2026-10-19 00:00 .. 2026-12-13 23:00 UTC (8 weeks). Read on or
  after **2026-12-14** by `score.py` (field `formal_read` in `scoreboard.json`), and written up in
  `READ_2026-12-14.md` whatever it shows.
- **Best free baseline:** of ATR(14) H1 and same-hour 20-day, the one with the lower pooled MSE-log over the same
  scored pair-hours (chosen after the fact, which favours the baselines).
- **Statistic:** for each scored hour, the mean over pairs of `MSE-log(best baseline) - MSE-log(model)`;
  Diebold-Mariano t with a Newey-West HAC variance, lag 24 hours.
- **PASS:** model pooled MSE-log lower than the best free baseline's **and** HAC t > 1.96.
  **FAIL:** model pooled MSE-log not lower. **INDETERMINATE:** lower, but t <= 1.96.
  At least 600 scored hours are needed; with fewer, the read is postponed week by week (Mondays) up to 2027-01-11
  and is then made with whatever exists, labelled underpowered.
- **What we expect (from back-data, not a promise):** product_check look B (MT5 feed, 2026-08-07..10-09) gave an MSE
  ratio of about 0.81 against the best free tool with research timing. Live timing and a different feed make it worse;
  see the README section "Calibration checks": with the live timing on Dukascopy
  data the ratio was about 0.88 (t = 3.9) on that window.
- **Secondary, cannot pass or fail the test:** release-hour subset (about 2 USD releases a week, so 8 weeks give
  only ~20 release hours per pair, mostly jobless claims), the hour after, QLIKE, MAE in pips, within +-25%, per pair.

## 7. Data discipline (embargo)
- The window **2026-10-10 00:00 .. 2026-10-18 23:59 UTC** is a sealed one-shot confirmation window (owner decision A,
  2026-10-17). No forecast is made for, no outcome is fetched for, and nothing is printed about any hour in it.
  The first live forecasts need lookback inputs (up to 35 days of one-minute bars, ATR, the 20-day same-hour mean)
  that cross it; those are read only inside the runner as inputs (registry rule D1: lookback inputs may cross a
  window). Raw data never leave the runner's private cache.
- Registered in the owner's embargo registry (source `apxtt-newsvol-live`): calibration SEEN to 2026-10-10, the
  sealed window, and this log as PROSPECTIVE from 2026-10-19 with the read on 2026-12-14.
- **Exemption E1 (recorded here, owner may revoke):** the registry flags the forward log of fx-vol-managed-carry-2026
  (PROSPECTIVE 2026-10-13..2028-09-16, daily/monthly vol forecasts on the same 7 majors) as related. That study's
  decisions are frozen and logged daily with no tuning possible, so publishing hourly ranges here cannot change it.
  The owner approved this public live log on 2026-10-17 ("Go"); this exemption is taken as covered by that approval
  and is flagged to the owner for confirmation.

## 8. What would make the log invalid, and what happens then
- A run that crashes or is delayed past the hour start produces a late or missing hour: it is counted, not hidden.
- If Dukascopy stops serving the hourly files, the log pauses; the gap is reported. Switching the data source is an
  amendment that starts a new scored window.
- The frozen files are never edited. A bug in `forecast.py` that changes a forecast is fixed only by an amendment;
  hours forecast under the bug are scored as they were logged.
- Event file: an event for a future hour may be added or corrected (e.g. an announced schedule change) at least 24 h
  before that hour, by a dated amendment. Nothing is changed for an hour already forecast.

## 9. Honest limits (also in the README)
- It forecasts the **size** of the move, never its direction. Next hour only.
- Back-tested on one broker's data; the live feed is Dukascopy, whose ranges differ a little.
- Release hours are rare; the 8-week read is about all hours. The release-hour claim needs many more weeks.
- Past accuracy does not guarantee future accuracy. Not financial advice.
