param(
  [string]$TaskName = "JobAggregatorMaintenance",
  [int]$DailyAtHour = 3,
  [int]$DailyAtMinute = 15,
  [int]$ReportRetentionDays = 30,
  [int]$LogRetentionDays = 14,
  [switch]$SkipVacuum
)

$ErrorActionPreference = "Stop"
if ($DailyAtHour -lt 0 -or $DailyAtHour -gt 23) { throw "DailyAtHour must be between 0 and 23." }
if ($DailyAtMinute -lt 0 -or $DailyAtMinute -gt 59) { throw "DailyAtMinute must be between 0 and 59." }

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runScript = Join-Path $repoRoot "ops\run_maintenance.ps1"
if (-not (Test-Path $runScript)) {
  throw "Missing run script: $runScript"
}

$timeText = "{0:D2}:{1:D2}" -f $DailyAtHour, $DailyAtMinute
$argParts = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", ('"{0}"' -f $runScript),
  "-ReportRetentionDays", "$ReportRetentionDays",
  "-LogRetentionDays", "$LogRetentionDays"
)
if ($SkipVacuum) { $argParts += "-SkipVacuum" }
$taskArgs = $argParts -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArgs -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $timeText
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Task registered: $TaskName"
Write-Host "Schedule: daily at $timeText"
Write-Host "Action: powershell.exe $taskArgs"
