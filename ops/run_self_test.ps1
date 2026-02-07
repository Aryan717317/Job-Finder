param(
  [string]$Query = "AI/ML Engineer",
  [switch]$Headful,
  [switch]$SendEmail,
  [switch]$AllowPreflightFail,
  [string[]]$Platform
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$argsList = @("self_test_runner.py", "--query", $Query)
if ($Headful) { $argsList += "--headful" }
if ($SendEmail) { $argsList += "--send-email" }
if ($AllowPreflightFail) { $argsList += "--allow-preflight-fail" }
foreach ($name in $Platform) {
  if (-not [string]::IsNullOrWhiteSpace($name)) {
    $argsList += @("--platform", $name)
  }
}

& $pythonExe @argsList
exit $LASTEXITCODE
