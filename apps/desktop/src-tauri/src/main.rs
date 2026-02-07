#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod models;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::start_scrape_run,
            commands::list_platform_support,
            commands::list_scrape_runs,
            commands::get_scrape_run,
            commands::get_scrape_run_jobs,
            commands::get_scrape_run_events,
        ])
        .run(tauri::generate_context!())
        .expect("error while running ajh-desktop");
}
