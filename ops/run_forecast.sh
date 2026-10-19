#!/usr/bin/env bash
# Run forecast.py once and write the commit message for ops/commit_push.sh (AMENDMENTS.md A1).
# Idempotent: forecast.py skips a target hour already in log/forecasts.jsonl, so this is safe to re-run after a
# reset to origin/main. Writes "forecast <target>" to <message-file>, or empties it when nothing was logged.
# Usage: bash ops/run_forecast.sh <message-file>
set -o pipefail
MSG=$1
OUT="${RUNNER_TEMP:-/tmp}/fc.out"
python forecast.py | tee "$OUT" || exit 1
T=$(grep -oP '^TARGET=\K.*' "$OUT" || true)
if [ -n "$T" ]; then echo "forecast $T" > "$MSG"; else : > "$MSG"; fi
