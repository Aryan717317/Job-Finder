use crate::models::{
    JobOut, PlatformSupportOut, RunDetail, RunEventOut, RunListItem, RunResponse, StartRunPayload,
};

const SCRAPER_BASE_URL: &str = "http://127.0.0.1:8081";

async fn parse_json_response<T: serde::de::DeserializeOwned>(
    response: reqwest::Response,
) -> Result<T, String> {
    if !response.status().is_success() {
        let body = response
            .text()
            .await
            .unwrap_or_else(|_| "<no body>".to_string());
        return Err(format!("Scraper service returned error: {body}"));
    }

    response
        .json::<T>()
        .await
        .map_err(|e| format!("Invalid scraper response: {e}"))
}

#[tauri::command]
pub async fn start_scrape_run(payload: StartRunPayload) -> Result<RunResponse, String> {
    let client = reqwest::Client::new();
    let response = client
        .post(format!("{SCRAPER_BASE_URL}/v1/runs"))
        .json(&payload)
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<RunResponse>(response).await
}

#[tauri::command]
pub async fn list_platform_support() -> Result<Vec<PlatformSupportOut>, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{SCRAPER_BASE_URL}/v1/platforms"))
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<Vec<PlatformSupportOut>>(response).await
}

#[tauri::command]
pub async fn list_scrape_runs(limit: Option<u32>) -> Result<Vec<RunListItem>, String> {
    let client = reqwest::Client::new();
    let mut url = reqwest::Url::parse(&format!("{SCRAPER_BASE_URL}/v1/runs"))
        .map_err(|e| format!("Invalid runs URL: {e}"))?;
    if let Some(value) = limit {
        url.query_pairs_mut()
            .append_pair("limit", &value.to_string());
    }

    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<Vec<RunListItem>>(response).await
}

#[tauri::command]
pub async fn get_scrape_run(run_id: String) -> Result<RunDetail, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{SCRAPER_BASE_URL}/v1/runs/{run_id}"))
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<RunDetail>(response).await
}

#[tauri::command]
pub async fn get_scrape_run_jobs(run_id: String) -> Result<Vec<JobOut>, String> {
    let client = reqwest::Client::new();
    let response = client
        .get(format!("{SCRAPER_BASE_URL}/v1/runs/{run_id}/jobs"))
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<Vec<JobOut>>(response).await
}

#[tauri::command]
pub async fn get_scrape_run_events(
    run_id: String,
    since_id: Option<i64>,
) -> Result<Vec<RunEventOut>, String> {
    let client = reqwest::Client::new();
    let mut url = reqwest::Url::parse(&format!("{SCRAPER_BASE_URL}/v1/runs/{run_id}/events"))
        .map_err(|e| format!("Invalid events URL: {e}"))?;

    if let Some(value) = since_id {
        url.query_pairs_mut()
            .append_pair("since_id", &value.to_string());
    }

    let response = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Failed to reach scraper service: {e}"))?;

    parse_json_response::<Vec<RunEventOut>>(response).await
}
