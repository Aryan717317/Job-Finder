param(
  [int]$Port = 5000
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$env:DASHBOARD_PORT = "$Port"
& $pythonExe app.py
exit $LASTEXITCODE
