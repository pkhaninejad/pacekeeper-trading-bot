mod config;
mod license;

use std::collections::HashMap;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
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

fn project_root() -> Result<PathBuf, String> {
    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("failed to resolve executable path: {e}"))?
        .parent()
        .ok_or("failed to resolve executable directory".to_string())?
        .to_path_buf();

    let mut cursor = exe_dir.as_path();
    for _ in 0..6 {
        if cursor.join("stock_bot.py").exists() && cursor.join("prediction_bot").exists() {
            return Ok(cursor.to_path_buf());
        }
        cursor = cursor
            .parent()
            .ok_or("could not find project root from executable location".to_string())?;
    }
    Err("could not find project root with stock_bot.py".to_string())
}

fn python_executable(root: &PathBuf) -> PathBuf {
    let unix = root.join(".venv/bin/python");
    if unix.exists() {
        return unix;
    }
    let win = root.join(".venv/Scripts/python.exe");
    if win.exists() {
        return win;
    }
    PathBuf::from("python")
}

fn bot_command(bot: &str, root: &PathBuf) -> Result<(PathBuf, Vec<String>), String> {
    let python = python_executable(root);
    match bot {
        "stock" => Ok((python, vec!["stock_bot.py".to_string()])),
        "prediction" => Ok((python, vec!["-m".to_string(), "prediction_bot.main".to_string()])),
        _ => Err(format!("unsupported bot: {bot}")),
    }
}

fn bot_port(bot: &str) -> u16 {
    match bot {
        "stock" => 4000,
        "prediction" => 4001,
        _ => 0,
    }
}

// Kill any process holding the given port so we can spawn fresh.
fn kill_port(port: u16) {
    if port == 0 { return; }
    #[cfg(unix)]
    let _ = Command::new("sh")
        .args(["-c", &format!("lsof -ti:{port} | xargs kill -9 2>/dev/null; true")])
        .status();
    #[cfg(windows)]
    let _ = Command::new("cmd")
        .args(["/C", &format!(
            "for /f \"tokens=5\" %a in ('netstat -aon ^| findstr \":{port} \"') do @taskkill /f /pid %a >nul 2>&1"
        )])
        .status();
}

#[tauri::command]
fn load_config(app: tauri::AppHandle) -> Result<Option<config::Config>, String> {
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    config::load_from_path(&config::config_path(&data_dir))
}

#[tauri::command]
fn save_config(app: tauri::AppHandle, mut config: config::Config) -> Result<(), String> {
    // Auto-detect project root when first completing setup so the installed
    // app can find the Python project even outside the source tree.
    if config.project_root.is_empty() {
        if let Ok(root) = project_root() {
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

    // Prefer the project_root saved in config (works for installed apps outside
    // the source tree); fall back to walking up from the executable (dev mode).
    let root = saved_cfg
        .as_ref()
        .filter(|c| !c.project_root.is_empty())
        .and_then(|c| {
            let p = PathBuf::from(&c.project_root);
            if p.join("stock_bot.py").exists() { Some(p) } else { None }
        })
        .map(Ok)
        .unwrap_or_else(project_root)?;

    if let Some(cfg) = saved_cfg {
        if cfg.setup_complete {
            config::write_env_to_path(&root.join(".env"), &cfg)?;
        }
    }

    // Kill anything holding the port (handles stale processes from prior sessions)
    kill_port(bot_port(&bot));

    let mut map = state
        .processes
        .lock()
        .map_err(|_| "process state poisoned".to_string())?;

    // Drop any tracked handle — port is already freed above
    map.remove(&bot);

    let (program, args) = bot_command(&bot, &root)?;
    let child = Command::new(program)
        .args(args)
        .current_dir(root)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
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
fn open_dashboard(bot: String, app: tauri::AppHandle) -> Result<(), String> {
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
        .plugin(tauri_plugin_updater::Builder::new().build())
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
                for (_, mut child) in map.drain() {
                    let _ = child.kill();
                }
            }
        });
}
