# Amendments

None yet. Each amendment is dated, says whether any live outcome existed when it was written, and never moves
the primary test in PREREGISTRATION.md.

## A0 (2026-10-18 00:10 UTC, before any live outcome exists; operational, not a rule change)
GitHub had not yet fired the hourly schedule ~2 h after it was committed (known start-up lag of GitHub's scheduler).
A backup schedule at minute 50 was added. It only matters when the minute-35 run did not log the next hour: a target
already in the log is skipped before anything is fetched. Same data cut (newest complete Dukascopy hour = the one
before the current hour); the on-time rule (pushed before the hour starts) is unchanged, so a backup run that pushes
after the hour starts is logged as late and not scored.
