# AJH Scraper Service

FastAPI + Playwright microservice for read-only job scraping and normalization.

## Platform Coverage
Implemented extractors:
- Arc.dev
- Cutshort
- FlexJobs
- Foundit
- Hirect
- Hirist
- Indeed
- Internshala
- LinkedIn
- Naukri
- Remote.co
- Relocate.me
- Remotive
- We Work Remotely
- Wellfound
- Working Nomads

Scaffolded adapters (stub mode; zero extraction until parser is implemented):
- None

## Local Run
```powershell
cd services/scraper
# Use Python 3.11-3.13 (recommended 3.12)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8081
```
From repo root (PowerShell wrappers):
```powershell
.\ops\run_scraper_api.ps1 -Port 8081 -Reload
.\ops\run_dashboard.ps1 -Port 5000
.\ops\run_maintenance.ps1 -ReportRetentionDays 30 -LogRetentionDays 14
```

## One-Off Full Cycle (CLI)
From repo root:
```powershell
python cycle_runner.py --query "AI/ML Engineer fresher 0-1 years"
```
Optional:
- `--platform <name>` (repeatable)
- `--headful`
- `--no-email`
- `--mode <label>`

## E2E Self-Test (Preflight + Scrape)
From repo root:
```powershell
python self_test_runner.py --query "AI/ML Engineer fresher 0-1 years"
```
Optional:
- `--platform <name>` (repeatable)
- `--headful`
- `--send-email`
- `--allow-preflight-fail`

## Preflight Only (CLI)
From repo root:
```powershell
python preflight_runner.py --timeout-seconds 30
```

## Local Deploy Orchestration
From repo root:
```powershell
.\ops\deploy_local.ps1 -Query "AI/ML Engineer" -StartApi -StartDashboard
.\ops\local_stack_status.ps1
.\ops\stop_local_stack.ps1
.\ops\stop_local_stack.ps1 -KillOrphans
```
If `.venv` is on unsupported Python:
```powershell
.\ops\recreate_venv.ps1 -PythonTag 3.12
```
Useful deploy flags:
- `-BasePythonExe py -BasePythonArg -3.12` to choose interpreter used for venv creation
- `-ForceRecreateVenv` to rebuild `.venv` with selected interpreter
- `-StartTimeoutSeconds 40` to control health-check wait time
- `-SkipStartupChecks` to skip API/dashboard health verification
- `-SkipModuleChecks` to skip Python import prechecks before bootstrap/start
- `-SkipInstall -SkipBrowserInstall -SkipBootstrap` for fast local restarts
- By default, `deploy_local` fails fast and cleans up background processes if startup health checks do not pass

## Scheduled Maintenance (Windows)
```powershell
.\ops\register_maintenance_task.ps1 -TaskName "JobAggregatorMaintenance" -DailyAtHour 3 -DailyAtMinute 15
.\ops\unregister_cycle_task.ps1 -TaskName "JobAggregatorMaintenance"
```

## Endpoints
- `GET /health`
- `GET /v1/platforms`
- `POST /v1/runs` (queued; returns immediately)
- `GET /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/jobs` (includes posted date, tags, salary/experience/employment text where available)
- `GET /v1/runs/{run_id}/events?since_id=0`

## Runtime Notes
- Runs execute in background tasks with max concurrency from `AJH_MAX_PARALLEL_RUNS`.
- Per-platform retries use `AJH_MAX_PLATFORM_RETRIES` with bounded exponential backoff.
- Per-run events are persisted in SQLite for polling from Tauri.
- Email send attempts are logged in SQLite (`email_notifications`).
- Full-cycle execution history is logged in SQLite (`cycle_runs`).
- Dashboard can be protected with HTTP Basic auth via env vars.
- Optional auto-cycle scheduler is controlled via `AUTO_CYCLE_ENABLED`, `AUTO_CYCLE_MINUTES`, and `AUTO_CYCLE_QUERY`.
- CLI runner log file path is controlled via `AJH_CYCLE_LOG_PATH`.
- Selector smoke-test reports are saved under `services/scraper/data/smoke_reports/`.
- Preflight reports are saved under `services/scraper/data/preflight_reports/`.
- E2E self-test reports are saved under `services/scraper/data/self_test_reports/`.
- Readiness rollup reports are saved under `services/scraper/data/readiness_reports/`.
- Maintenance reports are saved under `services/scraper/data/maintenance_reports/`.
- Local stack runtime state is tracked at `services/scraper/data/runtime/local_stack.json`.
