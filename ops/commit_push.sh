#!/usr/bin/env bash
# Commit and push log changes safely (AMENDMENTS.md A1). Used by .github/workflows/hourly.yml.
#
# Usage: bash ops/commit_push.sh <message-file> "<idempotent regenerate command>" <path>...
#   <message-file>  file holding the commit message (re-read on every attempt, so a regenerate command may change it;
#                   if it is missing or empty after a regenerate, there is nothing of ours left to push)
#   <regenerate>    re-creates this step's append on top of a fresh origin/main (forecast.py / score.py are
#                   idempotent: an hour already logged is skipped)
#
# Loop: commit -> fetch -> rebase onto origin/main -> ops/check_logs.py -> push.
# On a rebase conflict or a failed log check: abort the rebase, hard-reset to origin/main (dropping only our own
# unpushed commit), re-run the regenerate command and try again. A file with conflict markers, invalid JSON, a broken
# hash chain or an edited past line is never pushed. History is never rewritten on the remote (no force push).
# On success prints PUSHED=<sha> and PUSHED_UTC=<runner clock read right after the push returned>.
set -u
MSGFILE=$1; REGEN=$2; shift 2
PATHS=("$@")

sync_to_origin() {
  git rebase --abort >/dev/null 2>&1 || true
  git merge --abort >/dev/null 2>&1 || true
  git fetch -q origin main && git reset -q --hard origin/main
}

for i in 1 2 3 4 5 6; do
  git add -- "${PATHS[@]}" 2>/dev/null || true
  if ! git diff --cached --quiet; then
    if [ ! -s "$MSGFILE" ]; then echo "staged changes but no message file; refusing"; sync_to_origin; exit 1; fi
    git commit -q -F "$MSGFILE"
  fi
  if ! git fetch -q origin main; then echo "fetch failed (attempt $i)"; sleep $((i * 5)); continue; fi
  if [ "$(git rev-list --count origin/main..HEAD)" = "0" ]; then
    echo "nothing of ours to push (origin/main $(git rev-parse --short origin/main))"
    git reset -q --hard origin/main
    exit 0
  fi
  if ! git rebase -q origin/main; then
    echo "rebase conflict (attempt $i): abort, reset to origin/main, re-run: $REGEN"
    sync_to_origin
    if ! python ops/check_logs.py --base origin/main; then
      echo "origin/main itself fails the log check: STOP, nothing pushed (needs a human)"; exit 2
    fi
    bash -o pipefail -c "$REGEN" || { echo "regenerate command failed"; sync_to_origin; exit 1; }
    continue
  fi
  if [ "$(git rev-list --count origin/main..HEAD)" = "0" ]; then
    echo "after rebase nothing of ours is left (already on origin/main $(git rev-parse --short origin/main))"
    exit 0
  fi
  if ! python ops/check_logs.py --base origin/main; then
    echo "log check failed (attempt $i): reset to origin/main, re-run: $REGEN"
    sync_to_origin
    if ! python ops/check_logs.py --base origin/main; then
      echo "origin/main itself fails the log check: STOP, nothing pushed (needs a human)"; exit 2
    fi
    bash -o pipefail -c "$REGEN" || { echo "regenerate command failed"; sync_to_origin; exit 1; }
    continue
  fi
  if git push -q origin HEAD:main; then
    P=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "PUSHED=$(git rev-parse HEAD)"
    echo "PUSHED_UTC=$P"
    exit 0
  fi
  echo "push rejected (attempt $i); retrying"
  sleep $((i * 3))
done
echo "giving up after 6 attempts; working tree reset to origin/main"
sync_to_origin
exit 1
