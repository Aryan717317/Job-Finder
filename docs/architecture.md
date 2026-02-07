# AJH Architecture (Phase 1+)

## Components
1. Tauri Desktop App (Rust): scheduler, policy engine, local secrets bridge.
2. Scraper Service (Python): Playwright runners + platform adapters.
3. Data Layer (SQLite now, PostgreSQL later): runs, jobs, events, notification state.
4. Notifier Layer: Gmail SMTP sender for HTML job summaries.

## Runtime Flow
1. Desktop app submits `CreateRunRequest` to scraper service.
2. Scraper persists queued run and executes in background worker.
3. Jobs are normalized and persisted.
4. Events are persisted for live polling (`run.started`, `platform.*`, `run.completed`).
5. Notifier sends HTML summaries for unnotified jobs and marks them as notified.

## Platform Status
- Implemented: Arc.dev, Cutshort, FlexJobs, Foundit, Hirect, Hirist, Indeed, Internshala, LinkedIn, Naukri, Remote.co, Relocate.me, Remotive, We Work Remotely, Wellfound, Working Nomads
- Stubbed with runtime markers: none

## Scale-Out Plan
- Move queue execution to dedicated worker process.
- Migrate to PostgreSQL and add account/session vault references.
- Add scheduler service for periodic scrape + notify runs.
