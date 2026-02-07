param(
  [string]$Query = "AI/ML Engineer",
  [int]$ApiPort = 8081,
  [int]$DashboardPort = 5000,
  [int]$StartTimeoutSeconds = 40,
  [string]$BasePythonExe = "python",
  [string]$BasePythonArg = "",
  [switch]$ForceRecreateVenv,
  [switch]$SkipInstall,
  [switch]$SkipBrowserInstall,
  [switch]$SkipBootstrap,
  [switch]$SkipModuleChecks,
  [switch]$SkipStartupChecks,
  [switch]$StartApi,
  [switch]$StartDashboard,
  [switch]$ApiReload,
  [switch]$SelfTestSendEmail,
  [switch]$SelfTestAllowPreflightFail
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

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

function Get-PythonVersionInfo {
  param(
    [Parameter(Mandatory = $true)] [string]$PythonExe
  )
  $raw = & $PythonExe "-c" "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
  if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect Python version from: $PythonExe"
  }
  $versionText = ($raw | Select-Object -First 1).ToString().Trim()
  $parts = $versionText.Split(".")
  if ($parts.Count -lt 2) {
    throw "Unexpected Python version format from ${PythonExe}: $versionText"
  }
  return [ordered]@{
    major = [int]$parts[0]
    minor = [int]$parts[1]
    patch = if ($parts.Count -ge 3) { [int]$parts[2] } else { 0 }
    text = $versionText
  }
}

function Assert-SupportedPythonVersion {
  param(
    [Parameter(Mandatory = $true)] $VersionInfo,
    [Parameter(Mandatory = $true)] [string]$PythonLabel
  )
  $major = [int]$VersionInfo.major
  $minor = [int]$VersionInfo.minor
  if ($major -ne 3 -or $minor -lt 11 -or $minor -gt 13) {
    throw (
      "Unsupported Python version for this stack ($PythonLabel=$($VersionInfo.text)). " +
      "Use Python 3.11-3.13 (recommended 3.12), then recreate venv: " +
      ".\ops\deploy_local.ps1 -BasePythonExe py -BasePythonArg -3.12 -ForceRecreateVenv ..."
    )
  }
}

function Get-MissingPythonModules {
  param(
    [Parameter(Mandatory = $true)] [string]$PythonExe,
    [Parameter(Mandatory = $true)] [string[]]$Modules
  )
  $missing = @()
  foreach ($module in $Modules) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe "-c" "import $module" *> $null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($exitCode -ne 0) {
      $missing += $module
    }
  }
  return $missing
}

function Start-BackgroundScript {
  param(
    [Parameter(Mandatory = $true)] [string]$ScriptPath,
    [Parameter(Mandatory = $true)] [string[]]$Arguments,
    [Parameter(Mandatory = $true)] [string]$Label
  )
  $logDir = Join-Path $repoRoot "services\scraper\data\logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $stdoutPath = Join-Path $logDir "$Label.out.log"
  $stderrPath = Join-Path $logDir "$Label.err.log"

  $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath) + $Arguments
  $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argList -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

  return [ordered]@{
    label = $Label
    pid = $proc.Id
    stdout = $stdoutPath
    stderr = $stderrPath
    script = $ScriptPath
    args = $Arguments
  }
}

function Get-LogTail {
  param(
    [Parameter(Mandatory = $true)] [string]$Path,
    [int]$Lines = 20
  )
  if (-not (Test-Path $Path)) {
    return "<missing log file>"
  }
  try {
    return (Get-Content -Path $Path -Tail $Lines -ErrorAction Stop) -join "`n"
  } catch {
    return "<unable to read log>"
  }
}

function Wait-ForEndpoint {
  param(
    [Parameter(Mandatory = $true)] [string]$Url,
    [int]$TimeoutSeconds = 40
  )
  $deadline = (Get-Date).AddSeconds([Math]::Max(1, $TimeoutSeconds))
  $lastError = ""
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-RestMethod -Method Get -Uri $Url -TimeoutSec 3
      $statusText = ""
      if ($null -ne $resp -and ($resp.PSObject.Properties.Name -contains "status")) {
        $statusText = [string]$resp.status
      }
      return [ordered]@{
        ok = $true
        status = $statusText
        error = ""
      }
    } catch {
      $lastError = $_.Exception.Message
      Start-Sleep -Seconds 1
    }
  }
  return [ordered]@{
    ok = $false
    status = ""
    error = $lastError
  }
}

function Assert-ServiceReady {
  param(
    [Parameter(Mandatory = $true)] $Service,
    [Parameter(Mandatory = $true)] [string]$HealthUrl,
    [int]$TimeoutSeconds = 40
  )
  $proc = Get-Process -Id ([int]$Service.pid) -ErrorAction SilentlyContinue
  if ($null -eq $proc) {
    $stderrTail = Get-LogTail -Path ([string]$Service.stderr)
    throw "Service '$($Service.label)' exited early. stderr tail:`n$stderrTail"
  }

  $wait = Wait-ForEndpoint -Url $HealthUrl -TimeoutSeconds $TimeoutSeconds
  if (-not $wait.ok) {
    $stderrTail = Get-LogTail -Path ([string]$Service.stderr)
    throw "Service '$($Service.label)' failed health check at $HealthUrl within ${TimeoutSeconds}s. Last error: $($wait.error)`nstderr tail:`n$stderrTail"
  }
}

$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if ($ForceRecreateVenv -and (Test-Path $venvDir)) {
  Write-Host "Recreating virtual environment at .venv"
  Remove-Item -Recurse -Force $venvDir
}

if (-not (Test-Path $venvPython)) {
  Write-Host "Creating virtual environment at .venv"
  $venvArgs = @()
  if (-not [string]::IsNullOrWhiteSpace($BasePythonArg)) {
    $venvArgs += $BasePythonArg
  }
  $venvArgs += @("-m", "venv", ".venv")
  Run-OrThrow -Exe $BasePythonExe -Args $venvArgs
}
$pythonExe = $venvPython
$versionInfo = Get-PythonVersionInfo -PythonExe $pythonExe
Assert-SupportedPythonVersion -VersionInfo $versionInfo -PythonLabel $pythonExe
Write-Host ("Using Python {0} ({1})" -f $versionInfo.text, $pythonExe)

if (-not $SkipInstall) {
  Write-Host "Installing Python dependencies"
  Run-OrThrow -Exe $pythonExe -Args @("-m", "pip", "install", "--upgrade", "pip")
  Run-OrThrow -Exe $pythonExe -Args @("-m", "pip", "install", "-r", "services/scraper/requirements.txt")
}

if (-not $SkipBrowserInstall) {
  Write-Host "Installing Playwright browser: chromium"
  Run-OrThrow -Exe $pythonExe -Args @("-m", "playwright", "install", "chromium")
}

if (-not $SkipModuleChecks) {
  $requiredModules = @()
  if (-not $SkipBootstrap) {
    $requiredModules += @("fastapi", "flask", "uvicorn", "playwright", "pydantic")
  }
  if ($StartApi -or $StartDashboard) {
    $requiredModules += @("flask", "uvicorn", "fastapi", "playwright")
  }
  $requiredModules = $requiredModules | Sort-Object -Unique

  if ($requiredModules.Count -gt 0) {
    Write-Host ("Checking required Python modules: {0}" -f ($requiredModules -join ", "))
    $missingModules = Get-MissingPythonModules -PythonExe $pythonExe -Modules $requiredModules
    if ($missingModules.Count -gt 0) {
      throw (
        ("Missing Python module(s): {0}. " -f ($missingModules -join ", ")) +
        ("Run with installs enabled or run: {0} -m pip install -r services/scraper/requirements.txt" -f $pythonExe)
      )
    }
  }
}

if (-not $SkipBootstrap) {
  Write-Host "Running bootstrap verification"
  $bootstrapArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $repoRoot "ops\bootstrap_and_verify.ps1"),
    "-Query", $Query
  )
  if ($SelfTestSendEmail) { $bootstrapArgs += "-SendEmail" }
  if ($SelfTestAllowPreflightFail) { $bootstrapArgs += "-AllowPreflightFail" }
  & powershell.exe @bootstrapArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Bootstrap verification failed. Check readiness report."
  }
}

$started = @()
try {
  if ($StartApi) {
    Write-Host "Starting scraper API in background on port $ApiPort"
    $apiArgs = @("-Port", "$ApiPort")
    if ($ApiReload) { $apiArgs += "-Reload" }
    $apiSvc = Start-BackgroundScript `
      -ScriptPath (Join-Path $repoRoot "ops\run_scraper_api.ps1") `
      -Arguments $apiArgs `
      -Label "scraper_api"
    $apiSvc["health_url"] = "http://127.0.0.1:$ApiPort/health"
    $started += $apiSvc

    if (-not $SkipStartupChecks) {
      Write-Host "Waiting for scraper API health check..."
      Assert-ServiceReady -Service $apiSvc -HealthUrl $apiSvc["health_url"] -TimeoutSeconds $StartTimeoutSeconds
      Write-Host "Scraper API is healthy."
    }
  }

  if ($StartDashboard) {
    Write-Host "Starting dashboard in background on port $DashboardPort"
    $dashSvc = Start-BackgroundScript `
      -ScriptPath (Join-Path $repoRoot "ops\run_dashboard.ps1") `
      -Arguments @("-Port", "$DashboardPort") `
      -Label "dashboard"
    $dashSvc["health_url"] = "http://127.0.0.1:$DashboardPort/healthz"
    $started += $dashSvc

    if (-not $SkipStartupChecks) {
      Write-Host "Waiting for dashboard health check..."
      Assert-ServiceReady -Service $dashSvc -HealthUrl $dashSvc["health_url"] -TimeoutSeconds $StartTimeoutSeconds
      Write-Host "Dashboard is healthy."
    }
  }
} catch {
  foreach ($svc in $started) {
    $proc = Get-Process -Id ([int]$svc.pid) -ErrorAction SilentlyContinue
    if ($null -ne $proc) {
      Stop-Process -Id ([int]$svc.pid) -Force
    }
  }
  throw
}

if ($started.Count -gt 0) {
  $runtimeDir = Join-Path $repoRoot "services\scraper\data\runtime"
  New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
  $runtimePath = Join-Path $runtimeDir "local_stack.json"
  ($started | ConvertTo-Json -Depth 6) | Set-Content -Path $runtimePath -Encoding UTF8

  Write-Host ""
  Write-Host "Started background services:"
  foreach ($item in $started) {
    Write-Host ("- {0}: pid={1}" -f $item.label, $item.pid)
    if ($item.Contains("health_url")) {
      Write-Host ("  health={0}" -f $item.health_url)
    }
    Write-Host ("  stdout={0}" -f $item.stdout)
    Write-Host ("  stderr={0}" -f $item.stderr)
  }
  Write-Host ("Runtime file: {0}" -f $runtimePath)
}

Write-Host ""
Write-Host "Local deploy completed successfully."
