# JobFinder (AJH - Autonomous Job Hunter)

**Version:** 0.9.0
**Status:** Production
**Repository:** https://github.com/AniruddhAgrahari/jobscoutbot

---

## Overview

**JobFinder** is a production-grade autonomous job aggregation and notification system that continuously scrapes job listings from 16+ job platforms (Indian and global), stores them in a centralized database, applies intelligent relevance scoring, and delivers personalized email alerts to users.

The system is designed to eliminate manual job hunting across multiple platforms by automating discovery, aggregation, and notification in a unified pipeline.

---

## Core Features

### 1. **Multi-Platform Scraping**
- Scrapes from **16 platforms simultaneously** with parallel processing (4 concurrent):
  - Indian platforms: Naukri, Foundit, Hirect, Hirist, Internshala, Cutshort
  - Global platforms: LinkedIn, Indeed, Arc.dev, Wellfound, Remote.co, Remotive, We Work Remotely, Relocate.me, FlexJobs, Working Nomads
- **Intelligent retry logic** with exponential backoff for transient failures
- **CAPTCHA detection** with human handoff option
- **Persistent browser contexts** maintaining cookies/localStorage per platform
- **Anti-detection measures** using Playwright stealth mode

### 2. **Job Aggregation & Deduplication**
- **Centralized SQLite database** storing normalized job records
- **Unique external IDs** (SHA256 hash of platform:url) preventing duplicates
- **Metadata extraction:** Title, Company, Location, URL, Posted Date, Salary, Experience, Employment Type, Tags
- **Upsert logic** preserving notification flags across scrape cycles
- **7 database indexes** for sub-10ms query performance

### 3. **Semantic Job Relevance Scoring**
- **Keyword overlap analysis** comparing job titles/descriptions against search queries
- **Weighted scoring:**
  - 60% title match weight
  - 20% description match weight
  - 20% exact phrase bonus
- **0.0-1.0 relevance scale** enabling job ranking and filtering
- **Applied to all 16 platforms** for consistent relevance assessment

### 4. **Intelligent Email Notifications**
- **Rich HTML emails** with job details in formatted tables
- **Per-job information:** Platform, Title, Company, Location, Salary, Direct Link
- **Unnotified job queries** fetching only new/unseen jobs since last notification
- **Retry logic** (3 attempts with 2-second delays) ensuring delivery
- **Delivery logging** tracking status and errors for debugging

### 5. **Multiple Execution Modes**
- **GitHub Actions (Scheduled):** Daily automated run at 3:30 AM UTC with auto-database commit
- **REST API:** FastAPI service (port 8081) for programmatic scrape triggering
- **Web Dashboard:** Flask UI (port 5000) for manual operations and monitoring
- **CLI Tools:** Python scripts for full cycles, diagnostics, testing, and maintenance
- **Desktop Orchestrator:** Tauri-based Rust app for future UI enhancements

### 6. **Security & Protection**
- **CSRF Protection:** All dashboard forms include hidden security tokens
- **Secure Secrets:** Auto-generated Flask session keys using cryptographic randomness
- **Rate Limiting:** API endpoints throttled (5/min POST, 30/min GET) preventing abuse
- **Basic Authentication:** Optional username/password protection on dashboard
- **HTTPS Ready:** Deployable behind reverse proxy for encrypted communications

### 7. **Monitoring & Diagnostics**
- **Preflight Checks:** System health validation (DB, email, Playwright, platform registry)
- **Smoke Tests:** Selector validation across all platforms before production runs
- **Self-Tests:** End-to-end cycle testing with optional email verification
- **Event Sourcing:** Complete run timeline via fine-grained event logging
- **Maintenance Tasks:** Automated report cleanup (30-day retention) and database optimization

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────┐
│           JobFinder System (v0.9.0)              │
├─────────────────────────────────────────────────┤
│                                                   │
│  ╔═══════════════════════════════════════════╗  │
│  ║        USER INTERACTION LAYER              ║  │
│  ╠═══════════════════════════════════════════╣  │
│  ║  Flask Dashboard (Port 5000)               ║  │
│  ║  └─ REST API (Port 8081)                  ║  │
│  ║  └─ CLI Tools (cycle_runner.py)           ║  │
│  ║  └─ Desktop App (Tauri/Rust)              ║  │
│  ╚═══════════════════════════════════════════╝  │
│                    ↓ HTTP/JSON                   │
│  ╔═══════════════════════════════════════════╗  │
│  ║     SCRAPING & PROCESSING LAYER            ║  │
│  ╠═══════════════════════════════════════════╣  │
│  ║  Playwright Headless Browser (Chromium)    ║  │
│  ║  └─ 16 Platform Scrapers (Parallel 4x)    ║  │
│  ║  └─ Semantic Scoring Engine (0.0-1.0)     ║  │
│  ║  └─ Anti-Detection (Stealth + Headers)    ║  │
│  ║  └─ Retry Logic (Exponential Backoff)     ║  │
│  ║  └─ Error Recovery (CAPTCHA Detection)    ║  │
│  ╚═══════════════════════════════════════════╝  │
│                    ↓ Insert/Update               │
│  ╔═══════════════════════════════════════════╗  │
│  ║          DATA PERSISTENCE LAYER            ║  │
│  ╠═══════════════════════════════════════════╣  │
│  ║  SQLite Database (data/ajh.db)             ║  │
│  ║  └─ Tables: scrape_runs, jobs,             ║  │
│  ║    run_events, email_notifications,       ║  │
│  ║    cycle_runs                              ║  │
│  ║  └─ 7 Indexes (optimized queries)         ║  │
│  ║  └─ 500k+ job capacity, normalized schema║  │
│  ╚═══════════════════════════════════════════╝  │
│                    ↓ Ready for Query             │
│  ╔═══════════════════════════════════════════╗  │
│  ║      NOTIFICATION DELIVERY LAYER           ║  │
│  ╠═══════════════════════════════════════════╣  │
│  ║  Email Notifier (Gmail SMTP)               ║  │
│  ║  └─ Unnotified Jobs Query (Indexed)       ║  │
│  ║  └─ HTML Email Generation                 ║  │
│  ║  └─ Retry Logic (3 attempts)              ║  │
│  ║  └─ Delivery Logging & Analytics          ║  │
│  ╚═══════════════════════════════════════════╝  │
│                                                   │
└─────────────────────────────────────────────────┘
```

### Data Model

**Core Tables:**

1. **scrape_runs** - Execution records
   - Tracks query, platforms, status, job count, timing

2. **jobs** - Job listings (deduplicated by platform:url hash)
   - Title, Company, Location, URL, Salary, Experience, Tags
   - Semantic relevance score (0.0-1.0)
   - Notification flag for delivery tracking
   - Scraped timestamp for freshness ordering

3. **run_events** - Granular timelines
   - Event type (started, completed, failed, captcha_required, etc.)
   - Message and optional payload for debugging

4. **email_notifications** - Delivery history
   - Status, job count, recipient, subject, error logs
   - Enables failure analysis and retry statistics

5. **cycle_runs** - Full-cycle tracking
   - Mode (manual/scheduled/self-test/github_actions)
   - Job processing count and notification count
   - Execution timing and error messages

---

## Execution Flow

### Standard Daily Cycle (GitHub Actions)

```
3:30 AM UTC (Scheduled Daily)
    ↓
Checkout main branch
    ↓
Setup Python 3.11 + Playwright
    ↓
Run: python scraper.py
    ├─ Acquires cycle singleton lock (prevents concurrent runs)
    ├─ Create scrape_run record (status: queued)
    ├─ Launch 16 scrapers in parallel (4 concurrent max)
    │  ├─ Each scraper navigates to platform
    │  ├─ Searches with configured query
    │  ├─ Scrolls to load dynamic content
    │  ├─ Extracts job cards from DOM
    │  ├─ Applies semantic scoring to each job
    │  ├─ Handles CAPTCHAs (logs event, manual intervention required)
    │  ├─ Retries on transient errors (rate limit, timeout)
    │  └─ Returns JobRecord list
    ├─ Normalize jobs (deduplicate by external_id)
    ├─ Upsert into database (preserves is_notified flag)
    ├─ Update scrape_run status to completed
    ├─ Log run_events for timeline reconstruction
    ├─ Query for unnotified jobs since last run
    ├─ Generate HTML email with job details
    ├─ Send via Gmail SMTP with retry logic
    ├─ Mark jobs as notified (is_notified = 1)
    ├─ Log email_notification delivery status
    └─ Mark cycle_run as completed
    ↓
Git auto-commit: data/ajh.db + [skip ci]
    ↓
Database persisted to GitHub
```

### Manual Scraping (Dashboard/API)

```
User triggers manual scrape
    ↓
Create scrape_run, emit run.queued event
    ↓
[Same as Daily Cycle steps]
    ↓
Return results to user
    └─ Dashboard shows job count, run ID
    └─ API returns 202 Accepted with run_id
```

---

## Technology Stack

### Backend
- **Python 3.11-3.13** - Primary language
- **FastAPI 0.115.6** - REST API framework with async support
- **Flask 3.1.0** - Web dashboard framework
- **Uvicorn 0.34.0** - ASGI application server
- **Pydantic 2.10.5** - Data validation and serialization

### Browser Automation
- **Playwright 1.50.0** - Cross-browser automation (Chromium)
- **playwright-stealth 1.0.6** - Anti-bot detection evasion

### Data & Storage
- **SQLite 3.x** - Embedded database (no external DB needed)
- **python-dotenv 1.0.1** - Environment configuration

### Security & Rate Limiting
- **flask-wtf 1.2.2** - CSRF protection for forms
- **slowapi 0.1.9** - API rate limiting

### Serialization & Performance
- **orjson 3.10.15** - Fast JSON encoding/decoding

### Infrastructure
- **GitHub Actions** - CI/CD and scheduled automation
- **PowerShell** - Windows operations automation
- **Rust + Tauri 2** - Desktop orchestrator (optional)

---

## Directory Structure

```
JobFinder/
├── app.py                          # Flask dashboard (Port 5000)
├── notifier.py                     # Email notification system
├── cycle_runner.py                 # Full cycle CLI tool
├── scraper.py                      # GitHub Actions entry point
├── preflight_runner.py             # System diagnostics CLI
├── self_test_runner.py             # E2E testing CLI
├── maintenance_runner.py           # Cleanup & optimization CLI
│
├── templates/
│   └── dashboard.html              # Dashboard UI template (Jinja2)
│
├── services/scraper/
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Configuration template
│   │
│   └── app/
│       ├── main.py                 # FastAPI application (Port 8081)
│       ├── config.py               # Settings dataclass
│       ├── models.py               # JobRecord dataclass
│       ├── schemas.py              # Pydantic validation models
│       ├── db.py                   # SQLite database operations
│       ├── runner.py               # Scraping orchestration
│       ├── ranking.py              # Semantic scoring engine
│       ├── smoke.py                # Selector smoke tests
│       ├── preflight.py            # System health checks
│       ├── self_test.py            # E2E validation
│       ├── maintenance.py          # Cleanup tasks
│       │
│       └── scrapers/
│           ├── __init__.py         # Registry builder
│           ├── base.py             # BaseScraper abstract class
│           ├── stealth.py          # Anti-detection wrapper
│           ├── arc_dev.py          # Arc.dev scraper
│           ├── naukri.py           # Naukri scraper
│           ├── cutshort.py         # Cutshort scraper
│           ├── linkedin.py         # LinkedIn scraper
│           ├── wellfound.py        # Wellfound/AngelList scraper
│           ├── indeed.py           # Indeed scraper
│           ├── flexjobs.py         # FlexJobs scraper
│           ├── foundit.py          # Foundit scraper
│           ├── hirect.py           # Hirect scraper
│           ├── hirist.py           # Hirist scraper
│           ├── internshala.py      # Internshala scraper
│           ├── relocate_me.py      # Relocate.me scraper
│           ├── remotive.py         # Remotive scraper
│           ├── remote_co.py        # Remote.co scraper
│           ├── we_work_remotely.py # We Work Remotely scraper
│           ├── working_nomads.py   # Working Nomads scraper
│           └── platform_stubs.py   # Stub/placeholder scrapers
│
├── data/                           # Runtime data directory
│   ├── ajh.db                      # SQLite database (~114KB)
│   ├── preflight_reports/          # Health check results
│   ├── self_test_reports/          # E2E test results
│   ├── smoke_reports/              # Selector validation results
│   ├── maintenance_reports/        # Cleanup operation results
│   └── logs/                       # CLI execution logs
│
├── profiles/                       # Persistent browser profiles
│   ├── arc_dev/
│   ├── cutshort/
│   ├── linkedin/
│   ├── naukri/
│   └── ... (1 per platform)
│
├── ops/                            # Operations automation (PowerShell)
│   ├── deploy_local.ps1            # Full local deployment
│   ├── run_scraper_api.ps1         # Start FastAPI service
│   ├── run_dashboard.ps1           # Start Flask dashboard
│   ├── run_cycle.ps1               # Run single cycle
│   ├── local_stack_status.ps1      # Service status check
│   ├── stop_local_stack.ps1        # Stop all services
│   ├── bootstrap_and_verify.ps1    # Initial setup
│   ├── recreate_venv.ps1           # Virtual environment reset
│   ├── register_cycle_task.ps1     # Windows task scheduling
│   └── unregister_cycle_task.ps1   # Task removal
│
├── apps/desktop/                   # Tauri desktop application
│   ├── src-tauri/
│   │   ├── main.rs                 # Tauri entry point
│   │   ├── models.rs               # Rust data models
│   │   ├── commands.rs             # IPC commands
│   │   └── Cargo.toml              # Rust dependencies
│   └── README.md
│
├── .github/workflows/
│   └── job_scout.yml               # Daily GitHub Actions workflow
│
├── docs/
│   └── architecture.md             # System design documentation
│
├── README.md                       # User guide and quick start
├── AGENTS.md                       # Local Claude skills
├── PROJECT_OVERVIEW.md             # This file
└── .gitignore                      # Git ignore rules
```

---

## Configuration

### Environment Variables

```bash
# Database
AJH_DATABASE_URL=sqlite:///./data/ajh.db
AJH_DATA_DIR=./data
AJH_PROFILE_DIR=./profiles

# Scraping Behavior
AJH_ENV=dev|prod                    # Environment mode
AJH_TIMEOUT_MS=45000                # Page load timeout
AJH_LOCALE=en-IN                    # Browser locale
AJH_TIMEZONE=Asia/Kolkata           # Browser timezone

# Concurrency & Retry
AJH_MAX_PARALLEL_RUNS=2             # Concurrent scrape runs
AJH_MAX_PLATFORM_RETRIES=2          # Retries per platform
AJH_RETRY_BACKOFF_BASE_SECONDS=1.2  # Initial backoff
AJH_RETRY_BACKOFF_CAP_SECONDS=12.0  # Maximum backoff

# Email Notification (Gmail SMTP)
GMAIL_SENDER=your-email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  # App-specific password
GMAIL_RECIPIENT=recipient@example.com
EMAIL_MAX_RETRIES=3
EMAIL_RETRY_DELAY_SECONDS=2.0

# Dashboard Security
FLASK_SECRET_KEY=<auto-generated if not set>
DASHBOARD_USERNAME=admin            # Optional Basic auth
DASHBOARD_PASSWORD=secret123        # Optional Basic auth
DASHBOARD_PORT=5000

# Auto-Cycle Scheduler (Optional Background Runner)
AUTO_CYCLE_ENABLED=false
AUTO_CYCLE_MINUTES=60               # Interval between runs
AUTO_CYCLE_QUERY=AI/ML Engineer     # Default search query

# Logging
AJH_CYCLE_LOG_PATH=services/scraper/data/logs/cycle_runner.log
```

---

## REST API Endpoints

### Health & Platforms
- `GET /health` - Service health status
- `GET /v1/platforms` - Platform support status

### Run Management
- `POST /v1/runs` - Create new scrape run (Rate: 5/min)
- `GET /v1/runs` - List recent runs (Rate: 30/min)
- `GET /v1/runs/{run_id}` - Get run details (Rate: 30/min)

### Job Retrieval
- `GET /v1/runs/{run_id}/jobs` - Get jobs from run (Rate: 30/min)

### Event Streaming
- `GET /v1/runs/{run_id}/events?since_id=0` - Poll run events (Rate: 60/min)

---

## Usage

### Dashboard (Web UI)
```
Local: http://localhost:5000
Production: https://your-domain.com (behind reverse proxy)

Features:
├─ Manual scrape with custom query
├─ Send test email
├─ Full cycle (scrape + notify)
├─ Run diagnostics & tests
├─ View latest jobs with pagination
├─ Monitor email delivery history
└─ Auto-cycle scheduler configuration
```

### REST API
```bash
# Create a scrape run
curl -X POST http://localhost:8081/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python Engineer",
    "platforms": ["naukri", "linkedin", "cutshort"],
    "headless": true
  }'

# List recent runs
curl http://localhost:8081/v1/runs?limit=10

# Get jobs from run
curl http://localhost:8081/v1/runs/{run_id}/jobs

# Poll events (long-polling)
curl http://localhost:8081/v1/runs/{run_id}/events?since_id=0
```

### CLI
```bash
# Full cycle with optional email
python cycle_runner.py --query "Machine Learning Engineer" \
                       --platform naukri cutshort \
                       --no-email

# System preflight check
python preflight_runner.py

# Selector smoke test
python self_test_runner.py

# Cleanup reports (30 day retention)
python maintenance_runner.py
```

### Scheduled (GitHub Actions)
```
Automatically runs daily at 3:30 AM UTC
├─ Scrapes all 16 platforms
├─ Sends email notifications
└─ Auto-commits database to main branch
```

---

## Deployment Options

### Local Development
```bash
# Install dependencies
pip install -r services/scraper/requirements.txt
playwright install chromium

# Run services
python services/scraper/app/main.py  # FastAPI (port 8081)
python app.py                         # Flask (port 5000)

# Run cycles
python cycle_runner.py
```

### Docker Container
```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r services/scraper/requirements.txt
RUN playwright install chromium
CMD ["python", "cycle_runner.py"]
```

### Windows Automation (PowerShell)
```powershell
# Full deployment
.\ops\deploy_local.ps1

# Schedule daily runs
.\ops\register_cycle_task.ps1
```

### Cloud Deployment (GitHub Actions)
- Pre-configured daily at 3:30 AM UTC
- Auto-commits database to main branch
- Works with secrets for credentials

---

## Monitoring & Maintenance

### Health Checks
```bash
# API health
curl http://localhost:8081/health

# Dashboard health
curl http://localhost:5000/healthz
```

### Database Reports
- **Preflight:** System readiness (DB, email, Playwright, registry)
- **Smoke Test:** Selector validation across all platforms
- **Self-Test:** Full end-to-end cycle validation
- **Maintenance:** Cleanup old reports (30-day retention) and database optimization

### Logs
- Dashboard: `services/scraper/data/logs/cycle_runner.log`
- Reports: `data/preflight_reports/`, `data/self_test_reports/`, etc.
- Events: Stored in SQLite `run_events` table

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Scrape Duration** | 3-4 minutes (16 platforms in parallel) |
| **Database Queries** | <10ms with indexes |
| **Email Delivery** | <5s for 500 jobs |
| **Max Parallel Runs** | 2 (configurable) |
| **Job Capacity** | 500k+ (SQLite limit ~1GB) |
| **Database Size** | ~114KB per 5k jobs |
| **Dashboard Load** | <200ms cached, <500ms fresh query |

---

## Key Design Principles

1. **Simplicity Over Features** - SQLite instead of managed DB, minimal external dependencies
2. **Fault Tolerance** - Exponential backoff, CAPTCHA detection, platform retries
3. **Data Integrity** - Deduplication via hashing, upsert logic preserves flags, event sourcing
4. **Performance** - Parallel scraping, indexed queries, caching where appropriate
5. **Security** - CSRF protection, rate limiting, secure secret generation, optional auth
6. **Observability** - Fine-grained event logging, diagnostic reports, comprehensive metrics
7. **Maintainability** - Modular platform scrapers, separated concerns, type-safe code

---

## Future Enhancements

Based on current architecture, potential next steps:
- **Dedicated Worker Service** - Separate scraping queue from API server
- **PostgreSQL Migration** - Scale beyond SQLite for 1M+ jobs
- **Account Vault** - Authenticate on protected platforms (LinkedIn, Indeed)
- **Scheduler Service** - Independent cron orchestration layer
- **ML Pipeline** - Deep learning-based job relevance modeling
- **Desktop Refinement** - Complete Tauri UI with live timeline
- **Browser Extension** - One-click job bookmarking and filtering

---

## Support & Documentation

- **Main README:** `README.md` - Quick start and user guide
- **Architecture:** `docs/architecture.md` - System design deep dive
- **Local Skills:** `AGENTS.md` - Claude agent capabilities
- **GitHub Issues:** Check repo for known issues and discussions

---

**Last Updated:** February 2026
**Maintained By:** Aniruddhh Agrahari
**License:** See repository for license information
