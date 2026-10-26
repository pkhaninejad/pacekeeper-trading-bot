mod bots;
mod config;
mod license;

use std::collections::HashMap;
use std::fs::File;
use std::process::{Child, Command};
use std::time::Duration;
use std::sync::{Arc, Mutex};

use tauri::Manager;

#[derive(Clone)]
struct AppState {
    processes: Arc<Mutex<HashMap<String, Child>>>,
}

impl AppState {
    fn new() -> Self {
        Self {
            processes: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

#[tauri::command]
fn load_config(app: tauri::AppHandle) -> Result<Option<config::Config>, String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    config::load_from_path(&config::config_path(&data_dir))
}

#[tauri::command]
fn save_config(app: tauri::AppHandle, mut config: config::Config) -> Result<(), String> {
    // Remember the source checkout in dev mode; installed apps use the bundled sidecar.
    if config.project_root.is_empty() {
        if let Some(root) = bots::project_root() {
            config.project_root = root.to_string_lossy().to_string();
        }
    }
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    config::save_to_path(&config::config_path(&data_dir), &config)
}

#[tauri::command]
async fn test_t212_connection(key: String, secret: String, env: String) -> Result<String, String> {
    config::check_t212_connection(&key, &secret, &env).await
}

#[tauri::command]
async fn test_ai_connection(provider: String, key: String, endpoint: Option<String>, model: Option<String>) -> Result<String, String> {
    config::check_ai_connection(&provider, &key, endpoint.as_deref(), model.as_deref()).await
}

#[tauri::command]
fn check_license(key: String) -> Result<String, String> {
    let info = license::validate(&key)?;
    Ok(format!("Licensed to {}", info.email))
}

#[tauri::command]
fn get_license_info(app: tauri::AppHandle) -> Result<license::LicenseInfo, String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let cfg = config::load_from_path(&config::config_path(&data_dir))?
        .ok_or("No configuration found.".to_string())?;
    license::validate(&cfg.license_key)
}

#[tauri::command]
fn start_bot(bot: String, state: tauri::State<AppState>, app: tauri::AppHandle) -> Result<(), String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let cfg_path = config::config_path(&data_dir);
    let saved_cfg = config::load_from_path(&cfg_path)?;

    // Enforce license before starting any bot
    let license_key = saved_cfg.as_ref().map(|c| c.license_key.as_str()).unwrap_or("");
    license::validate(license_key).map_err(|e| format!("License error: {e}"))?;

    let saved_root = saved_cfg.as_ref().map(|c| c.project_root.as_str());
    let launch = bots::resolve(&bot, saved_root, &data_dir)?;

    if let Some(cfg) = &saved_cfg {
        if cfg.setup_complete {
            config::write_env_to_path(&launch.workdir.join(".env"), cfg)?;
        }
    }

    // Kill anything holding the port (handles stale processes from prior sessions)
    bots::kill_port(bots::port(&bot));

    let mut map = state
        .processes
        .lock()
        .map_err(|_| "process state poisoned".to_string())?;

    // Drop any tracked handle — port is already freed above
    map.remove(&bot);

    let log = File::create(launch.workdir.join(format!("{bot}.log")))
        .map_err(|e| format!("failed to create log file: {e}"))?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;
    let child = bots::hide_console(Command::new(&launch.program).args(&launch.args))
        .current_dir(&launch.workdir)
        .stdout(log)
        .stderr(log_err)
        .spawn()
        .map_err(|e| format!("failed to start {bot}: {e}"))?;

    map.insert(bot, child);
    Ok(())
}

#[tauri::command]
fn stop_bot(bot: String, state: tauri::State<AppState>) -> Result<(), String> {
    let mut map = state
        .processes
        .lock()
        .map_err(|_| "process state poisoned".to_string())?;

    if let Some(mut child) = map.remove(&bot) {
        child.kill().map_err(|e| format!("failed to stop {bot}: {e}"))?;
    }
    bots::kill_port(bots::port(&bot));
    Ok(())
}

#[tauri::command]
fn get_status(state: tauri::State<AppState>) -> Result<HashMap<String, String>, String> {
    let mut map = state
        .processes
        .lock()
        .map_err(|_| "process state poisoned".to_string())?;

    let mut status = HashMap::from([
        ("stock".to_string(), "stopped".to_string()),
        ("prediction".to_string(), "stopped".to_string()),
    ]);

    for (name, child) in map.iter_mut() {
        let running = child.try_wait().map_err(|e| e.to_string())?.is_none();
        status.insert(
            name.clone(),
            if running { "running" } else { "stopped" }.to_string(),
        );
    }

    map.retain(|_, child| child.try_wait().ok().flatten().is_none());
    Ok(status)
}

#[tauri::command]
async fn open_dashboard(bot: String, app: tauri::AppHandle) -> Result<(), String> {
    let (url_str, label, title) = match bot.as_str() {
        "stock"      => ("http://localhost:4000", "stock-dashboard",      "Pacekeeper — Stock Bot"),
        "prediction" => ("http://localhost:4001", "prediction-dashboard", "Pacekeeper — Prediction Bot"),
        _ => return Err(format!("unsupported bot: {bot}")),
    };

    // If the window is already open, bring it to front
    if let Some(win) = app.get_webview_window(label) {
        win.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let port = bots::port(&bot);
    tauri::async_runtime::spawn_blocking(move || bots::wait_for_port(port, Duration::from_secs(90)))
        .await
        .map_err(|e| e.to_string())??;

    let url: url::Url = url_str.parse().map_err(|e: url::ParseError| e.to_string())?;

    tauri::WebviewWindowBuilder::new(&app, label, tauri::WebviewUrl::External(url))
        .title(title)
        .inner_size(1440.0, 900.0)
        .min_inner_size(900.0, 600.0)
        .build()
        .map_err(|e| e.to_string())?;

    Ok(())
}

fn main() {
    let app = tauri::Builder::default()

        .plugin(tauri_plugin_process::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            start_bot, stop_bot, get_status, open_dashboard,
            load_config, save_config, test_t212_connection, test_ai_connection,
            check_license, get_license_info
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                let processes = {
                    let state = app.state::<AppState>();
                    state.processes.clone()
                };
                let mut map = match processes.lock() {
                    Ok(guard) => guard,
                    Err(_) => return,
                };
                for (bot, mut child) in map.drain() {
                    let _ = child.kill();
                    bots::kill_port(bots::port(&bot));
                }
            }
        });
}
