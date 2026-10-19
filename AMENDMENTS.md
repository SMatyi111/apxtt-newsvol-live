# Amendments

None yet. Each amendment is dated, says whether any live outcome existed when it was written, and never moves
the primary test in PREREGISTRATION.md.

## A0 (2026-10-18 00:20 UTC, before any live outcome exists; operational, not a rule change)
GitHub fired the first scheduled run about 38 minutes late. To keep forecasts on time, the workflow now runs at
minutes 15, 35 and 50 of every hour. Each run forecasts the next UTC hour; a target already in the log is skipped
before anything is fetched. A run before minute 45 logs only if every major has the freshest data the live timing
allows (newest complete Dukascopy hour = the one before the current hour, `features_lag_hours` = 2); otherwise it
leaves the hour to a later run. A run from minute 45 on logs what it has (the lag is in the record). The on-time
rule (pushed before the hour starts) and everything in PREREGISTRATION.md are unchanged.

## A1 (2026-10-19 07:15 UTC; written AFTER live outcomes exist: target hours 00:00 and 01:00 UTC have ended, but no realised range had been logged, fetched by hand or looked at; operational, not a rule change)
**What went wrong on 2026-10-19.**
- *Scoring crashed on every run.* `score.py` fetched the realised ranges of 00:00 and 01:00 correctly, then crashed
  while writing `scoreboard.json`: with fewer than 10 scored hours the Diebold-Mariano HAC t is NaN by design, and
  the file was written with `allow_nan=False` before the NaN-to-null clean-up. The step failed before its commit, so
  the realised records were never committed (`log/realized.jsonl` stayed empty and `hours_scored` stayed 0).
- *A receipt was lost.* The push receipt of the 06:00 forecast (pushed by run 39203233281 at about 05:24:20 UTC,
  commit `f146442`) was appended in the forecast step but only committed in the score step, which crashed.
- *A queued run started from a stale commit.* Run 39204333721 waited in the concurrency queue, then checked out the
  commit that was current when it was queued (`3370f5e`), not the tip of `main`; it re-forecast 06:00, its push was
  rejected, the rebase hit a conflict in `log/forecasts.jsonl`, and the runner's copy was left mid-rebase with
  conflict markers (the score step then failed on them). Nothing from that run reached `main`: the committed logs
  were checked and are intact (every line valid JSON, both hash chains OK).
- *GitHub skipped its schedule.* No scheduled run started between 01:18 and 05:11 UTC, nor between 05:24 and the
  push of this amendment, although the crons are set for minutes 15, 35 and 50.

**Hours lost (counted, not hidden).**
- 02:00, 03:00, 04:00, 05:00 UTC: no forecast. The only run in hour 01 (01:18) was early (before minute 45) and
  AUDUSD's newest hour had timed out (features lag 3), so under A0 it left 02:00 to a later run; GitHub then started
  no run until 05:11.
- 06:00 UTC: forecast logged, but without a receipt. Under PREREGISTRATION.md section 4 a forecast without a receipt
  is late, not scored. It stays in the log as it was written; GitHub's own push record is not substituted for the
  receipt.
- 07:00 UTC: no forecast (no run started in hour 06).
- Missing hours are excluded from the score, never imputed. The model, the frozen files, the scoring, the timing
  rule (a forecast counts only if pushed before its hour starts, else "late, not scored") and the PASS/FAIL rules are
  all unchanged.

**What changed (operational only).**
1. `score.py` writes NaN/inf as null in `scoreboard.json` (as the final write already did), so a short log no
   longer crashes it. Before doing anything it checks that every log line is a valid JSON object and both hash
   chains are intact; if not, it stops with exit code 3 and writes nothing. It never drops, rewrites or repairs a
   past line. `append_chained` refuses to append to an invalid file, an unterminated last line or a broken chain.
2. The workflow checks out the current tip of `main` (not the queued commit) and syncs to `origin/main` at the
   start of each step. The concurrency group (one run at a time, a running job is never cancelled) is kept.
3. Every commit goes through `ops/commit_push.sh`: commit, fetch, rebase onto `origin/main`, check, push, up to 6
   tries. On a rebase conflict or a failed check it aborts the rebase, resets to `origin/main` (dropping only its
   own unpushed commit) and re-runs the step's idempotent append (`forecast.py` and `score.py` skip an hour already
   logged). `ops/check_logs.py` must pass before any push: no conflict markers, valid JSON, intact chains, no target
   hour twice, and the `origin/main` version of each log is a byte prefix of the new one (append-only). If
   `origin/main` itself fails the check, the run stops and pushes nothing. No force push, no history rewrite.
4. The push receipt is committed and pushed immediately after the forecast push (`ops/append_receipt.py`), with
   the runner clock read right after that push returned, as before.
5. Backup trigger: the owner's PC dispatches the same workflow at minutes 20 and 45 of every hour (Windows task
   `apxtt-newsvol-trigger`, `ops/trigger_hourly.ps1`, `ops/install_trigger_task.ps1`). It only starts a GitHub run;
   all computation and every commit still happen on GitHub's runner, under the same rules. It runs only while the
   owner is logged on, so it reduces but does not remove the risk of skipped hours.
