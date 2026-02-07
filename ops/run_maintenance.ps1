param(
  [int]$ReportRetentionDays = 30,
  [int]$LogRetentionDays = 14,
  [switch]$SkipVacuum
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$argsList = @(
  "maintenance_runner.py",
  "--report-retention-days", "$ReportRetentionDays",
  "--log-retention-days", "$LogRetentionDays"
)
if ($SkipVacuum) {
  $argsList += "--skip-vacuum"
}

& $pythonExe @argsList
exit $LASTEXITCODE
