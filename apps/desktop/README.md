# AJH Desktop (Tauri) - Initial Scaffold

This Rust/Tauri layer triggers Python scraper runs via local HTTP.

## Current Commands
- `start_scrape_run`
- `list_platform_support`
- `list_scrape_runs`
- `get_scrape_run`
- `get_scrape_run_jobs`
- `get_scrape_run_events`

## Integration Contract
Expected scraper service base URL: `http://127.0.0.1:8081`

## Next Desktop Work
- Poll `/events` and render live run timeline.
- Add pause/resume/captcha-ack commands after worker state machine is added.
