param(
  [string]$TaskName = "JobAggregatorCycle",
  [int]$Minutes = 60,
  [int]$DailyAtHour = -1,
  [int]$DailyAtMinute = -1,
  [string]$Query = "AI/ML Engineer fresher 0-1 years",
  [switch]$NoEmail,
  [switch]$Headful
)

$ErrorActionPreference = "Stop"

$useDaily = ($DailyAtHour -ge 0 -or $DailyAtMinute -ge 0)
if ($useDaily) {
  if ($DailyAtHour -lt 0 -or $DailyAtHour -gt 23) {
    throw "DailyAtHour must be between 0 and 23."
  }
  if ($DailyAtMinute -lt 0 -or $DailyAtMinute -gt 59) {
    throw "DailyAtMinute must be between 0 and 59."
  }
} else {
  if ($Minutes -lt 1) {
    throw "Minutes must be >= 1."
  }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runScript = Join-Path $repoRoot "ops\run_cycle.ps1"
$vbsLauncher = Join-Path $repoRoot "ops\silent_launch.vbs"
if (-not (Test-Path $runScript)) {
  throw "Missing run script: $runScript"
}
if (-not (Test-Path $vbsLauncher)) {
  throw "Missing silent launcher: $vbsLauncher"
}

# Use wscript + VBS wrapper so no console window ever appears.
$argParts = @(
  '"' + $vbsLauncher + '"',
  '"' + $runScript + '"',
  "-Mode", "scheduled-task",
  "-Query", ('"' + $Query + '"')
)
if ($NoEmail) { $argParts += "-NoEmail" }
if ($Headful) { $argParts += "-Headful" }
$taskArgs = $argParts -join " "

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $taskArgs -WorkingDirectory $repoRoot
if ($useDaily) {
  $timeText = "{0:D2}:{1:D2}" -f $DailyAtHour, $DailyAtMinute
  $trigger = New-ScheduledTaskTrigger -Daily -At $timeText
} else {
  $trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
}
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Task registered: $TaskName"
if ($useDaily) {
  Write-Host ("Schedule: daily at {0:D2}:{1:D2}" -f $DailyAtHour, $DailyAtMinute)
} else {
  Write-Host "Schedule: every $Minutes minute(s)"
}
Write-Host "Action: powershell.exe $taskArgs"
