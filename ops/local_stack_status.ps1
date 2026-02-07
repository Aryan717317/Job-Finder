param(
  [int]$ApiPort = 8081,
  [int]$DashboardPort = 5000
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimePath = Join-Path $repoRoot "services\scraper\data\runtime\local_stack.json"

Write-Host "=== Local Stack Status ==="

if (Test-Path $runtimePath) {
  $items = Get-Content $runtimePath | ConvertFrom-Json
  if ($items -isnot [System.Array]) {
    $items = @($items)
  }
  Write-Host "Processes:"
  foreach ($item in $items) {
    $processId = [int]$item.pid
    $label = [string]$item.label
    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $state = if ($null -eq $proc) { "stopped" } else { "running" }
    Write-Host ("- {0}: pid={1} state={2}" -f $label, $processId, $state)
    if ($item.PSObject.Properties.Name -contains "health_url") {
      Write-Host ("  health={0}" -f $item.health_url)
    }
    Write-Host ("  stdout={0}" -f $item.stdout)
    Write-Host ("  stderr={0}" -f $item.stderr)
  }
} else {
  Write-Host "No runtime file: $runtimePath"
}

Write-Host ""
Write-Host "Endpoint checks:"

try {
  $api = Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:{0}/health" -f $ApiPort) -TimeoutSec 3
  Write-Host ("- API: ok status={0}" -f $api.status)
} catch {
  Write-Host "- API: unavailable"
}

try {
  $dash = Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:{0}/healthz" -f $DashboardPort) -TimeoutSec 3
  Write-Host ("- Dashboard: ok status={0}" -f $dash.status)
} catch {
  Write-Host "- Dashboard: unavailable"
}
