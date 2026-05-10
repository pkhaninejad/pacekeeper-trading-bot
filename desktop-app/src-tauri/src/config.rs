use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub setup_complete: bool,
    pub setup_step: u8,
    pub t212_api_key: String,
    pub t212_api_secret: String,
    #[serde(default = "default_t212_env")]
    pub t212_env: String,
    #[serde(default = "default_t212_account_type")]
    pub t212_account_type: String,
    #[serde(default = "default_ai_provider")]
    pub ai_provider: String,
    pub ai_api_key: String,
    #[serde(default)]
    pub ai_model: String,
    #[serde(default)]
    pub azure_endpoint: String,
    #[serde(default = "default_stop_loss_pct")]
    pub stop_loss_pct: f64,
    #[serde(default = "default_take_profit_pct")]
    pub take_profit_pct: f64,
    #[serde(default = "default_max_open_positions")]
    pub max_open_positions: u32,
    #[serde(default = "default_max_position_size_pct")]
    pub max_position_size_pct: f64,
    #[serde(default = "default_watchlist")]
    pub watchlist: Vec<String>,
    #[serde(default)]
    pub project_root: String,
    #[serde(default)]
    pub license_key: String,
}

fn default_t212_env() -> String { "demo".to_string() }
fn default_t212_account_type() -> String { "invest".to_string() }
fn default_ai_provider() -> String { "anthropic".to_string() }
fn default_stop_loss_pct() -> f64 { 0.02 }
fn default_take_profit_pct() -> f64 { 0.04 }
fn default_max_open_positions() -> u32 { 10 }
fn default_max_position_size_pct() -> f64 { 0.05 }
fn default_watchlist() -> Vec<String> {
    ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"]
        .iter().map(|s| s.to_string()).collect()
}

pub fn config_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("config.json")
}

pub fn load_from_path(path: &Path) -> Result<Option<Config>, String> {
    if !path.exists() {
        return Ok(None);
    }
    let raw = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let config: Config = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    Ok(Some(config))
}

pub fn save_to_path(path: &Path, config: &Config) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(config).map_err(|e| e.to_string())?;
    std::fs::write(path, json).map_err(|e| e.to_string())?;
    Ok(())
}

const WIZARD_KEYS: &[&str] = &[
    "T212_API_KEY", "T212_API_SECRET", "T212_ENV", "T212_ACCOUNT_TYPE",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_AI_KEY", "AZURE_AI_ENDPOINT",
    "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL", "AI_MODEL",
    "STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "MAX_OPEN_POSITIONS", "MAX_POSITION_SIZE_PCT",
    "WATCHLIST",
];

pub fn write_env_to_path(env_path: &Path, config: &Config) -> Result<(), String> {
    let mut preserved: Vec<String> = Vec::new();
    if env_path.exists() {
        let raw = std::fs::read_to_string(env_path).map_err(|e| e.to_string())?;
        for line in raw.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            if let Some(pos) = trimmed.find('=') {
                let key = &trimmed[..pos];
                if !WIZARD_KEYS.contains(&key) {
                    preserved.push(trimmed.to_string());
                }
            }
        }
    }

    let watchlist_json = serde_json::to_string(&config.watchlist).map_err(|e| e.to_string())?;

    let (ai_key_name, ai_key_val) = match config.ai_provider.as_str() {
        "openai"   => ("OPENAI_API_KEY",   config.ai_api_key.as_str()),
        "azure"    => ("AZURE_AI_KEY",     config.ai_api_key.as_str()),
        "gemini"   => ("GEMINI_API_KEY",   config.ai_api_key.as_str()),
        "deepseek" => ("DEEPSEEK_API_KEY", config.ai_api_key.as_str()),
        "ollama"   => ("OLLAMA_BASE_URL",  config.ai_api_key.as_str()),
        _          => ("ANTHROPIC_API_KEY", config.ai_api_key.as_str()),
    };

    let mut lines: Vec<String> = vec![
        format!("T212_API_KEY={}", config.t212_api_key),
        format!("T212_API_SECRET={}", config.t212_api_secret),
        format!("T212_ENV={}", config.t212_env),
        format!("T212_ACCOUNT_TYPE={}", config.t212_account_type),
        format!("{}={}", ai_key_name, ai_key_val),
        format!("STOP_LOSS_PCT={}", config.stop_loss_pct),
        format!("TAKE_PROFIT_PCT={}", config.take_profit_pct),
        format!("MAX_OPEN_POSITIONS={}", config.max_open_positions),
        format!("MAX_POSITION_SIZE_PCT={}", config.max_position_size_pct),
        format!("WATCHLIST={}", watchlist_json),
    ];

    if config.ai_provider == "azure" && !config.azure_endpoint.is_empty() {
        lines.push(format!("AZURE_AI_ENDPOINT={}", config.azure_endpoint));
    }
    if !config.ai_model.is_empty() {
        lines.push(format!("AI_MODEL={}", config.ai_model));
    }
    lines.extend(preserved);

    std::fs::write(env_path, lines.join("\n") + "\n").map_err(|e| e.to_string())?;
    Ok(())
}

pub async fn check_t212_connection(key: &str, secret: &str, env: &str) -> Result<String, String> {
    let base = if env == "live" {
        "https://live.trading212.com/api/v0"
    } else {
        "https://demo.trading212.com/api/v0"
    };
    let url = format!("{}/equity/account/info", base);
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .get(&url)
        .basic_auth(key, Some(secret))
        .send()
        .await
        .map_err(|e| {
            if e.is_timeout() || e.is_connect() {
                "Can't reach Trading 212. Check your internet connection and try again.".to_string()
            } else {
                format!("Network error: {}", e)
            }
        })?;
    match resp.status().as_u16() {
        200 => {
            let body: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
            let balance = body.get("cash")
                .and_then(|v| v.as_f64())
                .map(|v| format!("{:.2}", v))
                .unwrap_or_else(|| "connected".to_string());
            Ok(format!("Connected — cash balance: {}", balance))
        }
        401 => Err("Invalid API key or secret — double-check them in the T212 app under Settings → API.".to_string()),
        403 => Err("Your account doesn't have API access enabled. Contact T212 support.".to_string()),
        code => Err(format!("Unexpected response from Trading 212 (HTTP {}). Try again.", code)),
    }
}

pub async fn check_ai_connection(provider: &str, key: &str, endpoint: Option<&str>, model: Option<&str>) -> Result<String, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;

    match provider {
        "anthropic" => {
            let resp = client
                .post("https://api.anthropic.com/v1/messages")
                .header("x-api-key", key)
                .header("anthropic-version", "2023-06-01")
                .header("content-type", "application/json")
                .body(r#"{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}"#)
                .send()
                .await
                .map_err(|e| network_err(&e))?;
            match resp.status().as_u16() {
                200 | 201 => Ok("Connected — Anthropic API".to_string()),
                401 => Err("Invalid API key — make sure you copied the full key including the sk-ant- prefix.".to_string()),
                429 => Err("Key is valid but rate-limited. Wait a moment and test again.".to_string()),
                code => Err(format!("Unexpected response from Anthropic (HTTP {}). Try again.", code)),
            }
        }
        "openai" => {
            let resp = client
                .get("https://api.openai.com/v1/models")
                .bearer_auth(key)
                .send()
                .await
                .map_err(|e| network_err(&e))?;
            match resp.status().as_u16() {
                200 => Ok("Connected — OpenAI API".to_string()),
                401 => Err("Invalid API key — make sure you copied the full key.".to_string()),
                429 => Err("Key is valid but rate-limited. Wait a moment and test again.".to_string()),
                code => Err(format!("Unexpected response from OpenAI (HTTP {}). Try again.", code)),
            }
        }
        "azure" => {
            let ep = endpoint.unwrap_or("").trim().trim_end_matches('/');
            if ep.is_empty() {
                return Err("Azure endpoint URL is required.".to_string());
            }
            if key.is_empty() {
                return Err("Azure API key is required.".to_string());
            }
            let deployment = model.unwrap_or("").trim();
            if deployment.is_empty() {
                return Err("Enter your deployment name in the Model field first.".to_string());
            }

            // Validate credentials by listing models — no deployment name needed.
            // Try the traditional Azure OpenAI models endpoint first, then the v1 path.
            let base = ep.trim_end_matches("/openai/v1").trim_end_matches('/');
            let candidates = [
                format!("{}/openai/models?api-version=2024-12-01-preview", base),
                format!("{}/openai/v1/models", base),
                format!("{}/models", base),
            ];

            for url in &candidates {
                let resp = client
                    .get(url)
                    .header("api-key", key)
                    .send()
                    .await
                    .map_err(|e| network_err(&e))?;
                match resp.status().as_u16() {
                    200 => return Ok(format!("Connected — Azure key accepted, model «{}» saved.", deployment)),
                    401 | 403 => return Err("Invalid API key — double-check your Azure AI key.".to_string()),
                    _ => continue,
                }
            }

            // If none of the listing endpoints worked, try a chat completion and
            // accept DeploymentNotFound as proof the key itself is valid.
            let chat_url = format!("{}/openai/deployments/{}/chat/completions?api-version=2024-12-01-preview", base, deployment);
            let resp = client
                .post(&chat_url)
                .header("api-key", key)
                .header("content-type", "application/json")
                .body(r#"{"messages":[{"role":"user","content":"hi"}],"max_tokens":1}"#)
                .send()
                .await
                .map_err(|e| network_err(&e))?;
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            match status {
                200 | 201 => Ok(format!("Connected — Azure deployment «{}» verified.", deployment)),
                401 | 403 => Err("Invalid API key — double-check your Azure AI key.".to_string()),
                // DeploymentNotFound means the key was accepted — credentials are valid
                _ if body.contains("DeploymentNotFound") || body.contains("ResourceNotFound") => {
                    Ok(format!("Connected — Azure key accepted, model «{}» saved.", deployment))
                }
                400 if body.contains("max_tokens") => {
                    Ok(format!("Connected — Azure deployment «{}» verified.", deployment))
                }
                code => {
                    let snippet = body.chars().take(300).collect::<String>();
                    Err(format!("Azure returned HTTP {} — {}", code, snippet))
                }
            }
        }
        "ollama" => {
            let base = if key.is_empty() { "http://localhost:11434" } else { key };
            let resp = client
                .get(format!("{}/api/tags", base))
                .send()
                .await
                .map_err(|_| "Can't reach Ollama. Make sure it's running: ollama serve".to_string())?;
            if resp.status().is_success() {
                Ok("Connected — Ollama running locally".to_string())
            } else {
                Err(format!("Ollama responded with HTTP {}. Try again.", resp.status()))
            }
        }
        _ => {
            if key.is_empty() {
                Err("Please enter an API key.".to_string())
            } else {
                Ok("Key saved — connection test not available for this provider.".to_string())
            }
        }
    }
}

fn network_err(e: &reqwest::Error) -> String {
    if e.is_timeout() || e.is_connect() {
        "Network error — check your internet connection and try again.".to_string()
    } else {
        e.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_config() -> Config {
        Config {
            setup_complete: true,
            setup_step: 5,
            t212_api_key: "key123".to_string(),
            t212_api_secret: "secret456".to_string(),
            t212_env: "demo".to_string(),
            t212_account_type: "invest".to_string(),
            ai_provider: "anthropic".to_string(),
            ai_api_key: "sk-ant-xxx".to_string(),
            ai_model: "claude-sonnet-4-6".to_string(),
            azure_endpoint: String::new(),
            stop_loss_pct: 0.02,
            take_profit_pct: 0.04,
            max_open_positions: 10,
            max_position_size_pct: 0.05,
            watchlist: vec!["AAPL".to_string(), "TSLA".to_string()],
            project_root: String::new(),
        }
    }

    #[test]
    fn round_trip_save_load() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        let config = make_config();
        save_to_path(&path, &config).unwrap();
        let loaded = load_from_path(&path).unwrap().unwrap();
        assert_eq!(loaded.t212_api_key, "key123");
        assert_eq!(loaded.t212_api_secret, "secret456");
        assert_eq!(loaded.watchlist, vec!["AAPL", "TSLA"]);
        assert!(loaded.setup_complete);
        assert_eq!(loaded.setup_step, 5);
    }

    #[test]
    fn load_returns_none_when_missing() {
        let path = PathBuf::from("/tmp/__nonexistent_wizard_config_xyz__.json");
        let result = load_from_path(&path).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn save_creates_parent_dirs() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("subdir/nested/config.json");
        save_to_path(&path, &make_config()).unwrap();
        assert!(path.exists());
    }

    #[test]
    fn write_env_generates_correct_content() {
        let dir = tempfile::tempdir().unwrap();
        let env_path = dir.path().join(".env");
        let config = make_config();
        write_env_to_path(&env_path, &config).unwrap();
        let content = std::fs::read_to_string(&env_path).unwrap();
        assert!(content.contains("T212_API_KEY=key123"), "missing T212_API_KEY");
        assert!(content.contains("T212_ENV=demo"), "missing T212_ENV");
        assert!(content.contains("T212_ACCOUNT_TYPE=invest"), "missing T212_ACCOUNT_TYPE");
        assert!(content.contains("ANTHROPIC_API_KEY=sk-ant-xxx"), "missing ANTHROPIC_API_KEY");
        assert!(content.contains("STOP_LOSS_PCT=0.02"), "missing STOP_LOSS_PCT");
        assert!(content.contains("MAX_OPEN_POSITIONS=10"), "missing MAX_OPEN_POSITIONS");
        assert!(content.contains("WATCHLIST="), "missing WATCHLIST");
        assert!(content.contains("AI_MODEL=claude-sonnet-4-6"), "missing AI_MODEL");
    }

    #[test]
    fn write_env_preserves_non_wizard_keys() {
        let dir = tempfile::tempdir().unwrap();
        let env_path = dir.path().join(".env");
        std::fs::write(&env_path, "T212_API_KEY=old\nFINNHUB_API_KEY=fh123\nNEWS_API_KEY=news456\n").unwrap();
        write_env_to_path(&env_path, &make_config()).unwrap();
        let content = std::fs::read_to_string(&env_path).unwrap();
        assert!(content.contains("T212_API_KEY=key123"), "wizard key not updated");
        assert!(content.contains("FINNHUB_API_KEY=fh123"), "non-wizard key lost");
        assert!(content.contains("NEWS_API_KEY=news456"), "non-wizard key lost");
    }

    #[test]
    fn write_env_azure_provider_includes_endpoint() {
        let dir = tempfile::tempdir().unwrap();
        let env_path = dir.path().join(".env");
        let mut config = make_config();
        config.ai_provider = "azure".to_string();
        config.ai_api_key = "azure-key-abc".to_string();
        config.azure_endpoint = "https://my-resource.services.ai.azure.com/".to_string();
        write_env_to_path(&env_path, &config).unwrap();
        let content = std::fs::read_to_string(&env_path).unwrap();
        assert!(content.contains("AZURE_AI_KEY=azure-key-abc"));
        assert!(content.contains("AZURE_AI_ENDPOINT=https://my-resource.services.ai.azure.com/"));
        assert!(!content.contains("ANTHROPIC_API_KEY="));
    }

    #[test]
    fn write_env_openai_provider_sets_correct_key() {
        let dir = tempfile::tempdir().unwrap();
        let env_path = dir.path().join(".env");
        let mut config = make_config();
        config.ai_provider = "openai".to_string();
        config.ai_api_key = "sk-openai-xxx".to_string();
        write_env_to_path(&env_path, &config).unwrap();
        let content = std::fs::read_to_string(&env_path).unwrap();
        assert!(content.contains("OPENAI_API_KEY=sk-openai-xxx"));
        assert!(!content.contains("ANTHROPIC_API_KEY="));
    }
}
