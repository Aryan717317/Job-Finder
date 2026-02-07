use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StartRunPayload {
    pub query: String,
    pub platforms: Vec<String>,
    pub headless: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunResponse {
    pub run_id: String,
    pub status: String,
    pub query: String,
    pub platforms: Vec<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunListItem {
    pub run_id: String,
    pub status: String,
    pub query: String,
    pub platforms: Vec<String>,
    pub jobs_collected: i64,
    pub created_at: String,
    pub started_at: Option<String>,
    pub ended_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunDetail {
    pub run_id: String,
    pub status: String,
    pub query: String,
    pub platforms: Vec<String>,
    pub jobs_collected: i64,
    pub created_at: String,
    pub started_at: Option<String>,
    pub ended_at: Option<String>,
    pub error_message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JobOut {
    pub external_id: String,
    pub run_id: String,
    pub platform: String,
    pub title: String,
    pub company: String,
    pub location: String,
    pub url: String,
    pub posted_at: Option<String>,
    pub employment_type: String,
    pub salary_text: String,
    pub experience_text: String,
    pub tags: Vec<String>,
    pub semantic_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunEventOut {
    pub event_id: i64,
    pub run_id: String,
    pub event_type: String,
    pub message: String,
    pub payload: Option<serde_json::Value>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformSupportOut {
    pub platform: String,
    pub implemented: bool,
}
