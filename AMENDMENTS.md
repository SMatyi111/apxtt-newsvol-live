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
