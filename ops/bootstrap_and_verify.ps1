param(
  [string]$Query = "AI/ML Engineer",
  [switch]$CreateVenv,
  [switch]$InstallDeps,
  [switch]$InstallBrowser,
  [switch]$Headful,
  [switch]$SendEmail,
  [switch]$AllowPreflightFail,
  [string[]]$Platform,
  [double]$PreflightTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Parse-JsonFromOutput {
  param([Parameter(Mandatory = $true)] [object[]]$OutputLines)
  $lines = @()
  foreach ($item in @($OutputLines)) {
    if ($null -eq $item) { continue }
    $lines += ($item.ToString() -split "(`r`n|`n|`r)")
  }
  $lines = @($lines | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne "" })
  for ($i = $lines.Count - 1; $i -ge 0; $i--) {
    $line = [string]$lines[$i]
    if (-not ($line.StartsWith("{") -and $line.EndsWith("}"))) {
      continue
    }
    try {
      return $line | ConvertFrom-Json
    }
    catch {
      continue
    }
  }
  throw "Could not parse JSON from command output."
}

function Run-OrThrow {
  param(
    [Parameter(Mandatory = $true)] [string]$Exe,
    [Parameter(Mandatory = $true)] [string[]]$Args
  )
  & $Exe @Args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed: $Exe $($Args -join ' ') (ExitCode=$LASTEXITCODE)"
  }
}

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = ""

if (Test-Path $venvPython) {
  $pythonExe = $venvPython
}
elseif ($CreateVenv) {
  Write-Host "Creating virtual environment at .venv"
  Run-OrThrow -Exe "python" -Args @("-m", "venv", ".venv")
  $pythonExe = $venvPython
}
else {
  $pythonExe = "python"
}

if ($InstallDeps) {
  Write-Host "Installing Python dependencies"
  Run-OrThrow -Exe $pythonExe -Args @("-m", "pip", "install", "--upgrade", "pip")
  Run-OrThrow -Exe $pythonExe -Args @("-m", "pip", "install", "-r", "services/scraper/requirements.txt")
}

if ($InstallBrowser) {
  Write-Host "Installing Playwright browser: chromium"
  Run-OrThrow -Exe $pythonExe -Args @("-m", "playwright", "install", "chromium")
}

Write-Host "Running preflight diagnostics"
$preflightRaw = & $pythonExe "preflight_runner.py" "--timeout-seconds" "$PreflightTimeoutSeconds" 2>&1
$preflight = Parse-JsonFromOutput -OutputLines $preflightRaw

Write-Host "Running E2E self-test"
$selfArgs = @("self_test_runner.py", "--query", $Query, "--preflight-timeout-seconds", "$PreflightTimeoutSeconds")
if ($Headful) { $selfArgs += "--headful" }
if ($SendEmail) { $selfArgs += "--send-email" }
if ($AllowPreflightFail) { $selfArgs += "--allow-preflight-fail" }
foreach ($name in $Platform) {
  if (-not [string]::IsNullOrWhiteSpace($name)) {
    $selfArgs += @("--platform", $name)
  }
}
$selfRaw = & $pythonExe @selfArgs 2>&1
$selfTest = Parse-JsonFromOutput -OutputLines $selfRaw

$preflightOverall = if ($preflight.PSObject.Properties.Name -contains "report") { $preflight.report.overall_status } else { "fail" }
$selfStatus = if ($selfTest.PSObject.Properties.Name -contains "report") { $selfTest.report.status } else { "failed" }

$overall = "pass"
if ($preflightOverall -eq "fail" -or $selfStatus -eq "failed") {
  $overall = "fail"
}
elseif (
  $preflightOverall -eq "warning" -or
  $selfStatus -eq "skipped_preflight_fail" -or
  $selfStatus -eq "skipped_busy"
) {
  $overall = "warning"
}

$timestamp = (Get-Date).ToUniversalTime().ToString("o")
$readiness = [ordered]@{
  generated_at = $timestamp
  overall_status = $overall
  query = $Query
  python_executable = $pythonExe
  preflight = [ordered]@{
    overall_status = $preflightOverall
    summary = $preflight.report.summary
    report_path = $preflight.path
  }
  self_test = [ordered]@{
    status = $selfStatus
    selected_platforms = $selfTest.report.selected_platforms
    jobs_processed = $selfTest.report.jobs_processed
    notified_count = $selfTest.report.notified_count
    run_id = $selfTest.report.run_id
    error = $selfTest.report.error
    report_path = $selfTest.path
  }
}

$outDir = Join-Path $repoRoot "services\scraper\data\readiness_reports"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$latestPath = Join-Path $outDir "latest.json"
$stampedPath = Join-Path $outDir "$stamp.json"
$json = $readiness | ConvertTo-Json -Depth 8
Set-Content -Path $latestPath -Value $json -Encoding UTF8
Set-Content -Path $stampedPath -Value $json -Encoding UTF8

Write-Host ""
Write-Host "=== AJH Readiness Summary ==="
Write-Host ("Overall:        {0}" -f $readiness.overall_status)
Write-Host ("Preflight:      {0}" -f $readiness.preflight.overall_status)
Write-Host ("Self-Test:      {0}" -f $readiness.self_test.status)
Write-Host ("Jobs Processed: {0}" -f $readiness.self_test.jobs_processed)
Write-Host ("Notified:       {0}" -f $readiness.self_test.notified_count)
Write-Host ("Report:         {0}" -f $latestPath)
Write-Host ""

if ($overall -eq "fail") {
  exit 1
}
exit 0
