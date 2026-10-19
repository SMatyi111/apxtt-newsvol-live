# Registers the Windows scheduled task "apxtt-newsvol-trigger" (AMENDMENTS.md A1): runs ops/trigger_hourly.ps1 at
# minute 20 and minute 45 of every hour. Interactive logon (runs only while the owner is logged on): gh's token is in
# Windows Credential Manager, which S4U ("run whether logged on or not" without a password) cannot read.
# Re-running this script replaces the task. Run: powershell -NoProfile -ExecutionPolicy Bypass -File ops/install_trigger_task.ps1
$name = 'apxtt-newsvol-trigger'
$script = Join-Path $PSScriptRoot 'trigger_hourly.ps1'
# conhost --headless: no console window flashes on the desktop every half hour
$action = New-ScheduledTaskAction -Execute 'C:\Windows\System32\conhost.exe' `
    -Argument ('--headless powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $script)
$triggers = foreach ($m in 20, 45) {
    # local start time whose minute is $m; the PC clock is on a whole-hour offset from UTC, so minute $m local = UTC
    $start = (Get-Date).Date.AddMinutes($m)
    New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1)
}
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Principal $principal -Settings $settings `
    -Description 'Backup dispatch of github.com/SMatyi111/apxtt-newsvol-live hourly.yml at :20 and :45 (AMENDMENTS.md A1). Log: ops/logs/trigger.log' `
    -Force | Out-Null
Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime, LastRunTime, LastTaskResult
