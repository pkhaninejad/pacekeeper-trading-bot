use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, Instant};

const SIDECAR: &str = "pacekeeper-bots";

pub struct Launch {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub workdir: PathBuf,
}

fn exe_dir() -> Result<PathBuf, String> {
    std::env::current_exe()
        .map_err(|e| format!("failed to resolve executable path: {e}"))?
        .parent()
        .map(Path::to_path_buf)
        .ok_or("failed to resolve executable directory".to_string())
}

// Source checkout containing stock_bot.py (dev mode only).
pub fn project_root() -> Option<PathBuf> {
    let exe_dir = exe_dir().ok()?;
    exe_dir
        .ancestors()
        .take(7)
        .find(|dir| dir.join("stock_bot.py").exists() && dir.join("prediction_bot").exists())
        .map(Path::to_path_buf)
}

fn python_executable(root: &Path) -> PathBuf {
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

fn source_args(bot: &str) -> Vec<String> {
    match bot {
        "stock" => vec!["stock_bot.py".into()],
        _ => vec!["-m".into(), "prediction_bot.main".into()],
    }
}

// Prefer a source checkout (dev), otherwise the bundled sidecar running in app data.
pub fn resolve(bot: &str, saved_root: Option<&str>, data_dir: &Path) -> Result<Launch, String> {
    if bot != "stock" && bot != "prediction" {
        return Err(format!("unsupported bot: {bot}"));
    }

    let source = saved_root
        .filter(|r| !r.is_empty())
        .map(PathBuf::from)
        .filter(|p| p.join("stock_bot.py").exists())
        .or_else(project_root);
    if let Some(root) = source {
        return Ok(Launch {
            program: python_executable(&root),
            args: source_args(bot),
            workdir: root,
        });
    }

    let sidecar = exe_dir()?.join(format!("{SIDECAR}{}", std::env::consts::EXE_SUFFIX));
    if !sidecar.exists() {
        return Err(format!("bot runtime missing: {} not found — please reinstall Pacekeeper", sidecar.display()));
    }
    let workdir = data_dir.join("bots");
    std::fs::create_dir_all(&workdir).map_err(|e| format!("failed to create {}: {e}", workdir.display()))?;
    Ok(Launch { program: sidecar, args: vec![bot.to_string()], workdir })
}

pub fn port(bot: &str) -> u16 {
    match bot {
        "stock" => 4000,
        "prediction" => 4001,
        _ => 0,
    }
}

pub fn wait_for_port(port: u16, timeout: Duration) -> Result<(), String> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err(format!("dashboard on port {port} did not start within {}s", timeout.as_secs()))
}

pub fn hide_console(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd
}

// Kill any process holding the given port so we can spawn fresh.
pub fn kill_port(port: u16) {
    if port == 0 { return; }
    #[cfg(unix)]
    let _ = Command::new("sh")
        .args(["-c", &format!("lsof -ti:{port} | xargs kill -9 2>/dev/null; true")])
        .status();
    #[cfg(windows)]
    let _ = hide_console(Command::new("cmd").args(["/C", &format!(
            "for /f \"tokens=5\" %a in ('netstat -aon ^| findstr \":{port} \"') do @taskkill /f /pid %a >nul 2>&1"
        )]))
        .status();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_rejects_unknown_bot() {
        assert!(resolve("crypto", None, Path::new(".")).is_err());
    }

    #[test]
    fn resolve_prefers_saved_source_root() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("stock_bot.py"), "").unwrap();
        let launch = resolve("stock", dir.path().to_str(), Path::new(".")).unwrap();
        assert_eq!(launch.workdir, dir.path());
        assert_eq!(launch.args, vec!["stock_bot.py"]);
    }

    #[test]
    fn wait_for_port_times_out_on_closed_port() {
        assert!(wait_for_port(1, Duration::from_millis(100)).is_err());
    }
}
