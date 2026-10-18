# Amendments

None yet. Each amendment is dated, says whether any live outcome existed when it was written, and never moves
the primary test in PREREGISTRATION.md.

## A0 (2026-10-18 00:05 UTC, before any live outcome exists; operational, not a rule change)
GitHub had not yet fired the hourly schedule ~2 h after it was committed (known start-up lag of GitHub's scheduler).
A second schedule at minute 05 was added for redundancy. It forecasts the same next hour with the same data cut
(the newest complete Dukascopy hour is still the one before the current hour); whichever run logs a target first
wins, the other skips it before fetching anything. The on-time rule (pushed before the hour starts) is unchanged.
