# Autonomous Job Hunter (AJH)

Production-oriented scaffold for an autonomous job-hunting assistant targeting Indian and global platforms.

## Current Scope
- Python scraper microservice (FastAPI + Playwright) + Flask dashboard
- 20-platform registry (20 implemented extractors + 0 stubs)
- SQLite persistence for runs, jobs, and notification state
- Rust/Tauri orchestration command contracts (legacy path)

## Monorepo Layout
- `apps/desktop/src-tauri`: Rust/Tauri orchestrator scaffold
- `services/scraper`: Python scraping microservice
- `docs/architecture.md`: system architecture and execution flow

## Quick Start (Scraper Service)
```powershell
cd services/scraper
# Use Python 3.11-3.13 (recommended 3.12)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8081
```

## Quick Start (Dashboard + Notifier)
```powershell
python app.py
```
Dashboard actions:
- Manual Scrape
- Send Test Email
- Run Full Cycle (Scrape + Notify)
- Run Selector Smoke Test
- Run Preflight
- Run E2E Self-Test
- Run Maintenance
- Auto Cycle Scheduler (env-controlled)

## CLI Cycle Runner
```powershell
python cycle_runner.py --query "AI/ML Engineer fresher 0-1 years"
```
Optional flags:
- `--platform <name>` (repeatable, defaults to all implemented)
- `--headful`
- `--no-email`
- `--mode <label>`
Windows wrappers:
```powershell
.\ops\run_cycle.ps1 -Query "AI/ML Engineer fresher 0-1 years"
.\ops\run_dashboard.ps1 -Port 5000
.\ops\run_scraper_api.ps1 -Port 8081
.\ops\run_self_test.ps1 -Query "AI/ML Engineer"
.\ops\run_maintenance.ps1 -ReportRetentionDays 30 -LogRetentionDays 14
.\ops\bootstrap_and_verify.ps1 -Query "AI/ML Engineer"
```
Local deployment orchestration:
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
Task Scheduler helpers:
```powershell
.\ops\register_cycle_task.ps1 -TaskName "JobAggregatorCycle" -Minutes 60 -Query "AI/ML Engineer fresher 0-1 years"
.\ops\register_maintenance_task.ps1 -TaskName "JobAggregatorMaintenance" -DailyAtHour 3 -DailyAtMinute 15
.\ops\unregister_cycle_task.ps1 -TaskName "JobAggregatorCycle"
.\ops\unregister_cycle_task.ps1 -TaskName "JobAggregatorMaintenance"
```
E2E self-test CLI:
```powershell
python self_test_runner.py --query "AI/ML Engineer"
```
Preflight CLI:
```powershell
python preflight_runner.py --timeout-seconds 30
```

## API Quick Check
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8081/v1/runs -ContentType "application/json" -Body '{"query":"AI/ML Engineer","platforms":["cutshort","wellfound"],"headless":true}'
```
Dashboard health check:
```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:5000/healthz
```

## Important Notes
- Respect each platform's Terms of Service and robots restrictions.
- Use manual handoff for CAPTCHA and suspicious login challenges.
- Keep per-account low-rate automation to reduce flag risk.
- Gmail notifier requires: `GMAIL_SENDER`, `GMAIL_APP_PASSWORD`, `GMAIL_RECIPIENT`.
- Optional dashboard auth: `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`.
- Email retry controls: `EMAIL_MAX_RETRIES`, `EMAIL_RETRY_DELAY_SECONDS`.
- Optional scheduler: `AUTO_CYCLE_ENABLED`, `AUTO_CYCLE_MINUTES`, `AUTO_CYCLE_QUERY`.
- CLI log path: `AJH_CYCLE_LOG_PATH`.
- Readiness reports: `services/scraper/data/readiness_reports/`.
- Maintenance reports: `services/scraper/data/maintenance_reports/`.
