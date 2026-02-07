param(
  [string]$PythonTag = "3.12",
  [switch]$KeepExisting
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Write-Host "Checking Python launcher for version $PythonTag..."
& py "-$PythonTag" "--version"
if ($LASTEXITCODE -ne 0) {
  throw "Python $PythonTag not found via py launcher."
}

if ((Test-Path $venvDir) -and (-not $KeepExisting)) {
  Write-Host "Removing existing .venv"
  Remove-Item -Recurse -Force $venvDir
}

if (-not (Test-Path $venvPython)) {
  Write-Host "Creating .venv using py -$PythonTag"
  & py "-$PythonTag" "-m" "venv" ".venv"
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create .venv with Python $PythonTag"
  }
}

Write-Host "Virtual environment ready at .venv"
& $venvPython "-c" "import sys; print(sys.version)"
