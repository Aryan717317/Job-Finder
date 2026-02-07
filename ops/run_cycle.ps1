param(
  [string]$Query = "AI/ML Engineer",
  [switch]$NoEmail,
  [switch]$Headful,
  [string[]]$Platform,
  [string]$Mode = "scheduled-task"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$argsList = @("cycle_runner.py", "--query", $Query, "--mode", $Mode)
if ($NoEmail) { $argsList += "--no-email" }
if ($Headful) { $argsList += "--headful" }
foreach ($name in $Platform) {
  if (-not [string]::IsNullOrWhiteSpace($name)) {
    $argsList += @("--platform", $name)
  }
}

& $pythonExe @argsList
exit $LASTEXITCODE
