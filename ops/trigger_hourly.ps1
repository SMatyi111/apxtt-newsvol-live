# Backup trigger for the hourly live-log workflow (AMENDMENTS.md A1).
# GitHub skipped every scheduled run between 01:18 and 05:11 UTC on 2026-10-19, so the owner's PC also dispatches
# the workflow at minutes 20 and 45 of every hour (Windows scheduled task "apxtt-newsvol-trigger", Interactive logon,
# because gh keeps its token in Windows Credential Manager, which an S4U task cannot read).
# This script only asks GitHub to start a run; the GitHub runner still does every computation and every commit.
# The workflow's concurrency group queues overlapping runs, and forecast.py / score.py are idempotent per hour.
# Log: ops/logs/trigger.log (not committed).
$ErrorActionPreference = 'Continue'
$repo = 'SMatyi111/apxtt-newsvol-live'
$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'trigger.log'
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
function Write-Log($msg) {
    $line = '{0} {1}' -f (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
}
# keep the log small: last 5000 lines
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) {
    $keep = Get-Content $log -Tail 5000
    Set-Content -Path $log -Value $keep -Encoding utf8
}
try {
    $out = & $gh workflow run hourly.yml -R $repo 2>&1 | Out-String
    $code = $LASTEXITCODE
    Write-Log ("dispatch exit={0} {1}" -f $code, ($out -replace '\s+', ' ').Trim())
    exit $code
} catch {
    Write-Log ("dispatch FAILED: {0}" -f $_.Exception.Message)
    exit 1
}
