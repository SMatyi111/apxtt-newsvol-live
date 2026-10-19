# APXTT News Volatility Warning: public live log

An hourly, public, preregistered test of one forecast: **how big will the next hour's range be** on 7 major FX pairs
(EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD), compared with two free tools a trader already has:
ATR(14) on the hourly chart and the 20-day average range of the same hour.

- Every hour, a GitHub Action (`.github/workflows/hourly.yml`, minutes 15 / 35 / 50, plus a backup dispatch at minutes 20 / 45; see AMENDMENTS.md A0, A1) commits the forecasts for the **next** hour
  to `log/forecasts.jsonl` **before that hour starts**.
- After the hour, a later run adds the actual range (Dukascopy BID prices) to `log/realized.jsonl` and rebuilds
  `scoreboard.json`, which the website reads: <https://smatyi111.github.io/apextradingtools/news-volatility.html#live>
- The rules (what counts, what is scored, when the first formal read is, what PASS and FAIL mean) were fixed and
  committed **before the first scored hour** in [PREREGISTRATION.md](PREREGISTRATION.md) (tag `prereg-v1`).
  Results are published whatever they show.
- **Log start: Monday 2026-10-19 00:00 UTC. First formal read: 2026-12-14** (8 weeks).

## Frozen model
| file | SHA-256 |
|---|---|
| `model/coefficients.csv` | `21663b2aedcd6ecec87a6d13f482b4c4d87adb2ae261d1a9eb035a5c8d18ced4` |
| `model/events_utc.csv` | `da1da082e25f011829ac4320144098b84dc82e891328ff31be8acef7bbb65e1b` |

Every forecast record carries both hashes. Check them yourself: `sha256sum model/coefficients.csv model/events_utc.csv`.

## What the model is
A regression on the log of the hour's high-low range: time of day, weekday and month on the FX day clock
(New York + 7 h), recent one-minute realised volatility split into continuous and jump parts (HAR-CJ), a market-wide
volatility factor from all 28 G8 pairs, and 12 scheduled releases (NFP, US CPI, FOMC, ECB, BoE, US jobless claims,
US PPI, ISM, BoC, RBA, SNB, BoJ) for the release hour and the hour after. It was fitted on one broker's MT5 data,
2018-06..2026-10-09, and given one per-pair intercept for the Dukascopy feed (see PREREGISTRATION.md section 3).
Nothing on or after 2026-10-10 was used for fitting.

## What the back-data said (not live results)
From the original study (one MT5 broker feed, fitted 2018-06..2023-12, scored 2024-01..2026-08, median of 28 pairs):
- In the hour of a scheduled release for the pair's own currency, the range forecast missed by about a third as much
  as the best free tool and a fifth as much as ATR (squared log error). ATR under-calls release hours by 2-3x.
- EURUSD, NFP hour: average error 27 pips, vs 41 for the same-hour average and 51 for ATR(14) (30 releases).
- Ordinary hours: slightly better than the free tools (4.35 vs 5.08 pips error on a 14-pip average hour).

## Calibration checks for this log (already-seen data)

All on already-seen data, medians of the 7 majors. MSE-log = mean squared error of the log range forecast (the
primary loss). "lag2" = the live timing: the newest data at forecast time end one hour before the current hour; the
baselines get the same cut.

1. **The code reproduces the research.** `calibration/fit.py` on the research's MT5 inputs (fit 2018-06..2023-12,
   scored 2024-01..2026-08-06) reproduces product_check's per-pair MSE-log, MAE and n for FULL, ATR and the same-hour
   average (max difference 3e-16). Its production fit equals the MT5 product's coefficients (difference < 1e-14).
2. **Same back-test with the live timing (MT5, 2024-01..2026-08-06, ~16,100 hours per pair):** model MSE-log 0.171
   (0.157 with research timing), same-hour 20-day 0.219, ATR(14) 0.303; MAE 3.97 / 4.41 / 5.28 pips. Release hours
   (276 per pair): 0.232 / 0.627 / 1.213, MAE 11.7 / 15.3 / 21.0 pips. Pooled Diebold-Mariano t (2024-01..2026-10-09):
   12.3 vs the same-hour average, 40.2 vs ATR. The live timing costs about 9% MSE and keeps the ranking.
3. **Feed check on Dukascopy (`calibration/feed_adjust.py`).** Coefficients fitted on MT5 up to 2026-08-06, scored
   out of sample on 2026-08-07..2026-10-09 (~1,090 hours per pair), Dukascopy BID data fetched by
   `.github/workflows/calibration-sample.yml`:

   | 2026-08-07..10-09, out of sample | MT5, research timing | MT5, live timing | **Dukascopy, live timing** |
   |---|---|---|---|
   | model MSE-log | 0.150 | 0.174 | **0.172** |
   | same-hour 20-day MSE-log | 0.193 | 0.193 | **0.195** |
   | ATR(14) H1 MSE-log | 0.294 | 0.316 | **0.306** |
   | MAE pips: model / same-hour / ATR | 2.96 / 3.51 / 4.04 | 3.20 / 3.51 / 4.18 | **3.21 / 3.52 / 4.24** |
   | pooled DM t, model vs same-hour / vs ATR | 6.5 / 13.9 | 3.9 / 13.7 | **3.9 / 13.1** |
   | release hours (18 per pair) MSE-log: model / same-hour / ATR | 0.22 / 0.94 / 1.62 | 0.24 / 0.94 / 1.66 | **0.23 / 0.93 / 1.68** |

   The feed changes almost nothing (the two feeds' hourly closes differ by a median 0.1-0.3 pip on the majors). The
   live timing costs most of the model's edge over the same-hour average outside release hours (MSE ratio about
   0.88 instead of 0.78), but the ranking held with t = 3.9 on a 9-week window, about the length of the first read.
4. **Feed intercepts** (mean log error on Dukascopy over that window, live timing; added to each forecaster's log
   forecast; same treatment for all three), in `model/coefficients.csv` as `d_model`, `d_atr`, `d_sh20`: between
   -0.05 and +0.05 for every pair and forecaster (`calibration/output/feed_intercepts.csv`).
5. **Tick files = candles.** One-minute bars built from Dukascopy's hourly BID tick files equal its BID one-minute
   candle file exactly (EURUSD and USDJPY, 2026-09-02, 5 hours each; `calibration/check_ticks.py`).

Not done: a full re-fit on Dukascopy history (PREREGISTRATION.md section 3 explains why).

## Honest limits
- It forecasts the **size** of the move, not its direction. It is not a trading signal.
- **Next hour only.** For the next day it is no better than ATR(14) on the daily chart, so no daily claim is made.
- Live timing is harder than the back-test: a forecast must be committed before the hour starts, and Dukascopy
  publishes an hour's data shortly after it ends, so the newest data used is from the hour before the current one.
- Release hours are rare (about 2 a week per pair, half of them US jobless claims). The 8-week read is about all hours.
- Fitted on one broker's data; your broker's ranges may differ. Past accuracy does not guarantee future accuracy.
  Not financial advice.

## How to verify
1. **Timing:** each forecast is in a commit named `forecast <hour>`; `log/receipts.jsonl` holds the runner's UTC time
   right after that push, and GitHub's own push record and Actions logs show when it landed. A forecast pushed at or
   after its hour starts is marked late and not scored.
2. **No edits:** `log/*.jsonl` are append-only hash chains (each record's `prev_hash` is the previous record's `hash`;
   `hash` = SHA-256 of the record's canonical JSON without `hash`):
   `python -c "from newsvol.live import *; print(verify_chain(FORECASTS), verify_chain(REALIZED))"`.
3. **Outcomes:** recompute any hour's range from the public Dukascopy tick file named in PREREGISTRATION.md.
4. **Scores:** `python score.py --no-fetch` rebuilds `scoreboard.json` from the logs.

## Files
- `forecast.py`, `score.py`, `newsvol/`: the live code (Python 3.12, numpy, pandas).
- `model/`: the frozen coefficients and event calendar.
- `calibration/`: how the frozen numbers were made and checked (`fit.py`, `feed_adjust.py`, `fetch_history.py`,
  `check_ticks.py`, `output/`).
- `log/`: forecasts, realised ranges, push receipts, and `warmup.jsonl` (pre-start self-tests on old data, never scored).
- Raw price files are never committed (data licence): only forecasts and the hourly ranges derived from them.

The data come from Dukascopy's public historical datafeed. This project is not affiliated with Dukascopy.
