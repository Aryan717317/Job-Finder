param(
  [int]$Port = 8081,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$argsList = @(
  "-m", "uvicorn",
  "services.scraper.app.main:app",
  "--host", "127.0.0.1",
  "--port", "$Port"
)
if ($Reload) {
  $argsList += "--reload"
}

& $pythonExe @argsList
exit $LASTEXITCODE
