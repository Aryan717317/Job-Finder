param(
  [switch]$KillOrphans
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimePath = Join-Path $repoRoot "services\scraper\data\runtime\local_stack.json"

if (-not (Test-Path $runtimePath)) {
  Write-Host "No runtime file found: $runtimePath"
  exit 0
}

$items = Get-Content $runtimePath | ConvertFrom-Json
if ($items -isnot [System.Array]) {
  $items = @($items)
}

foreach ($item in $items) {
  $processId = [int]$item.pid
  $label = [string]$item.label
  $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($null -eq $proc) {
    Write-Host ("Process already stopped: {0} (pid={1})" -f $label, $processId)
    continue
  }
  Stop-Process -Id $processId -Force
  Write-Host ("Stopped: {0} (pid={1})" -f $label, $processId)
}

Remove-Item $runtimePath -Force
Write-Host "Removed runtime file."

if ($KillOrphans) {
  Write-Host "Scanning for orphan stack processes..."
  $candidates = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like "python*.exe" -and
    $_.CommandLine -and
    $_.CommandLine.Contains($repoRoot) -and
    (
      $_.CommandLine.Contains("app.py") -or
      $_.CommandLine.Contains("services.scraper.app.main:app")
    )
  }

  foreach ($proc in $candidates) {
    try {
      Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction Stop
      Write-Host ("Stopped orphan process pid={0}" -f $proc.ProcessId)
    } catch {
      Write-Host ("Unable to stop orphan process pid={0}" -f $proc.ProcessId)
    }
  }
}
