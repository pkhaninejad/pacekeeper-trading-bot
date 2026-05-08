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

#[tauri::command]
fn start_bot(bot: String, state: tauri::State<AppState>) -> Result<(), String> {
    let root = project_root()?;
    let mut map = state
        .processes
        .lock()
        .map_err(|_| "process state poisoned".to_string())?;

    if let Some(existing) = map.get_mut(&bot) {
        if existing.try_wait().map_err(|e| e.to_string())?.is_none() {
            return Ok(());
        }
    }

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
fn open_dashboard(bot: String) -> Result<(), String> {
    let url = match bot.as_str() {
        "stock" => "http://localhost:4000",
        "prediction" => "http://localhost:4001",
        _ => return Err(format!("unsupported bot: {bot}")),
    };

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(url)
            .spawn()
            .map_err(|e| format!("failed to open dashboard: {e}"))?;
    }

    #[cfg(target_os = "windows")]
    {
        Command::new("cmd")
            .args(["/C", "start", "", url])
            .spawn()
            .map_err(|e| format!("failed to open dashboard: {e}"))?;
    }

    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(url)
            .spawn()
            .map_err(|e| format!("failed to open dashboard: {e}"))?;
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![start_bot, stop_bot, get_status, open_dashboard])
        .run(tauri::generate_context!(), |app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                let state = app.state::<AppState>();
                if let Ok(mut map) = state.processes.lock() {
                    for (_, mut child) in map.drain() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .expect("error while running tauri application");
}
