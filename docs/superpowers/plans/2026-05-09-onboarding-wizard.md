# Onboarding Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-run setup wizard to the Tauri desktop app so non-technical users can configure the trading bot without editing any files.

**Architecture:** `App.tsx` calls `invoke("load_config")` on boot. If `config.json` is absent or `setup_complete=false`, it renders `<SetupWizard />` instead of the launcher. The wizard saves progress after each step. On completion `start_bot` writes a `.env` from `config.json` before spawning Python. A Settings panel (gear icon) lets users edit config at any time.

**Tech Stack:** Tauri v2, React 18, TypeScript, Rust + reqwest (HTTP tests), Vitest + @testing-library/react

**Spec:** `docs/superpowers/specs/2026-05-09-onboarding-wizard-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `desktop-app/src-tauri/src/config.rs` | Config struct, load/save, write_env, connection tests |
| Modify | `desktop-app/src-tauri/src/main.rs` | Add `mod config;`, register new commands, extend `start_bot` |
| Modify | `desktop-app/src-tauri/Cargo.toml` | Add `reqwest`, `tempfile` (dev) |
| Create | `desktop-app/src/types/config.ts` | TypeScript `Config` interface + defaults |
| Create | `desktop-app/src/components/wizard/SetupWizard.tsx` | Wizard container, step routing, save-on-advance |
| Create | `desktop-app/src/components/wizard/WizardProgress.tsx` | Progress bar |
| Create | `desktop-app/src/components/wizard/StepWelcome.tsx` | Step 1 — welcome screen |
| Create | `desktop-app/src/components/wizard/StepT212.tsx` | Step 2 — T212 keys + test |
| Create | `desktop-app/src/components/wizard/StepAIProvider.tsx` | Step 3 — AI provider + test |
| Create | `desktop-app/src/components/wizard/StepRiskProfile.tsx` | Step 4 — risk sliders |
| Create | `desktop-app/src/components/wizard/StepWatchlist.tsx` | Step 5 — watchlist |
| Create | `desktop-app/src/components/wizard/StepDone.tsx` | Done/success transition screen |
| Create | `desktop-app/src/components/SettingsPanel.tsx` | Settings modal (gear icon) |
| Create | `desktop-app/src/__tests__/setup.ts` | Vitest global setup, Tauri mock |
| Create | `desktop-app/src/__tests__/*.test.tsx` | Component tests |
| Modify | `desktop-app/src/App.tsx` | Conditional render wizard vs launcher + gear icon |
| Modify | `desktop-app/src/styles.css` | Wizard + settings styles |
| Modify | `desktop-app/package.json` | Add vitest + testing-library |
| Modify | `desktop-app/vite.config.ts` | Add test config block |

---

### Task 1: Create feature branch

- [ ] **Step 1: Create and switch to the feature branch**

```bash
git checkout -b feat/onboarding-wizard-issue-81
```

---

### Task 2: Add Rust and Node dependencies

**Files:**
- Modify: `desktop-app/src-tauri/Cargo.toml`
- Modify: `desktop-app/package.json`
- Modify: `desktop-app/vite.config.ts`

- [ ] **Step 1: Add reqwest and tempfile to Cargo.toml**

Open `desktop-app/src-tauri/Cargo.toml`. Replace the `[dependencies]` and add `[dev-dependencies]`:

```toml
[dependencies]
tauri = { version = "2.0", features = [] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
reqwest = { version = "0.12", features = ["json"] }

[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 2: Verify Rust compiles**

```bash
cd /path/to/project && cargo check --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: no errors.

- [ ] **Step 3: Add Vitest and Testing Library to package.json**

In `desktop-app/package.json`, add to `"devDependencies"`:

```json
"vitest": "^1.6.0",
"@testing-library/react": "^16.0.0",
"@testing-library/user-event": "^14.5.2",
"@testing-library/jest-dom": "^6.4.0",
"jsdom": "^24.0.0"
```

- [ ] **Step 4: Add test config to vite.config.ts**

Replace the full content of `desktop-app/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
  },
});
```

- [ ] **Step 5: Install Node deps**

```bash
cd desktop-app && pnpm install
```

Expected: lock file updated, no errors.

- [ ] **Step 6: Create Vitest global setup file**

Create `desktop-app/src/__tests__/setup.ts`:

```typescript
import "@testing-library/jest-dom";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: vi.fn().mockReturnValue(false),
}));
```

- [ ] **Step 7: Commit**

```bash
git add desktop-app/src-tauri/Cargo.toml desktop-app/package.json desktop-app/pnpm-lock.yaml desktop-app/vite.config.ts desktop-app/src/__tests__/setup.ts
git commit -m "chore: add reqwest, vitest, and testing-library dependencies"
```

---

### Task 3: Config struct + load/save (Rust)

**Files:**
- Create: `desktop-app/src-tauri/src/config.rs`
- Modify: `desktop-app/src-tauri/src/main.rs` (add `mod config;`)

- [ ] **Step 1: Create config.rs with failing tests**

Create `desktop-app/src-tauri/src/config.rs`:

```rust
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
            stop_loss_pct: 0.02,
            take_profit_pct: 0.04,
            max_open_positions: 10,
            max_position_size_pct: 0.05,
            watchlist: vec!["AAPL".to_string(), "TSLA".to_string()],
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
}
```

- [ ] **Step 2: Add `mod config;` to main.rs**

At the top of `desktop-app/src-tauri/src/main.rs`, after `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]` (if present) and before the `use` imports, add:

```rust
mod config;
```

- [ ] **Step 3: Run the Rust tests**

```bash
cargo test --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected output:
```
test config::tests::load_returns_none_when_missing ... ok
test config::tests::round_trip_save_load ... ok
test config::tests::save_creates_parent_dirs ... ok

test result: ok. 3 passed
```

- [ ] **Step 4: Commit**

```bash
git add desktop-app/src-tauri/src/config.rs desktop-app/src-tauri/src/main.rs
git commit -m "feat: add Config struct with load/save and Rust unit tests"
```

---

### Task 4: write_env_to_path (Rust)

**Files:**
- Modify: `desktop-app/src-tauri/src/config.rs`

- [ ] **Step 1: Write failing tests**

Add the following to the `#[cfg(test)]` block in `config.rs`, inside `mod tests`:

```rust
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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cargo test --manifest-path desktop-app/src-tauri/Cargo.toml 2>&1 | grep -E "FAILED|error\[" | head -5
```

Expected: compilation error — `write_env_to_path` not found.

- [ ] **Step 3: Implement write_env_to_path**

Add after `save_to_path` in `config.rs` (before `#[cfg(test)]`):

```rust
const WIZARD_KEYS: &[&str] = &[
    "T212_API_KEY", "T212_API_SECRET", "T212_ENV", "T212_ACCOUNT_TYPE",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_AI_KEY", "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "MAX_OPEN_POSITIONS", "MAX_POSITION_SIZE_PCT",
    "WATCHLIST",
];

pub fn write_env_to_path(env_path: &Path, config: &Config) -> Result<(), String> {
    // Preserve existing non-wizard keys
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
    lines.extend(preserved);

    std::fs::write(env_path, lines.join("\n") + "\n").map_err(|e| e.to_string())?;
    Ok(())
}
```

- [ ] **Step 4: Run all Rust tests**

```bash
cargo test --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src-tauri/src/config.rs
git commit -m "feat: add write_env_to_path preserving non-wizard keys"
```

---

### Task 5: Connection test commands (Rust)

**Files:**
- Modify: `desktop-app/src-tauri/src/config.rs`

No unit tests here — these make live HTTP calls. Verified manually after wiring in Task 6.

- [ ] **Step 1: Add check_t212_connection**

Add after `write_env_to_path` in `config.rs`:

```rust
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
```

- [ ] **Step 2: Add check_ai_connection**

Add after `check_t212_connection` in `config.rs`:

```rust
pub async fn check_ai_connection(provider: &str, key: &str) -> Result<String, String> {
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
```

- [ ] **Step 3: Compile check**

```bash
cargo check --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add desktop-app/src-tauri/src/config.rs
git commit -m "feat: add T212 and AI connection test commands (Rust)"
```

---

### Task 6: Wire Tauri commands in main.rs

**Files:**
- Modify: `desktop-app/src-tauri/src/main.rs`

- [ ] **Step 1: Add load_config and save_config commands**

Add these four functions in `main.rs` before `fn main()`:

```rust
#[tauri::command]
fn load_config(app: tauri::AppHandle) -> Result<Option<config::Config>, String> {
    use tauri::Manager;
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    config::load_from_path(&config::config_path(&data_dir))
}

#[tauri::command]
fn save_config(app: tauri::AppHandle, config: config::Config) -> Result<(), String> {
    use tauri::Manager;
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    config::save_to_path(&config::config_path(&data_dir), &config)
}

#[tauri::command]
async fn test_t212_connection(key: String, secret: String, env: String) -> Result<String, String> {
    config::check_t212_connection(&key, &secret, &env).await
}

#[tauri::command]
async fn test_ai_connection(provider: String, key: String) -> Result<String, String> {
    config::check_ai_connection(&provider, &key).await
}
```

- [ ] **Step 2: Extend start_bot to write .env before spawning**

In `main.rs`, update the `start_bot` signature to accept `app: tauri::AppHandle` and write the `.env` before spawning:

```rust
#[tauri::command]
fn start_bot(bot: String, state: tauri::State<AppState>, app: tauri::AppHandle) -> Result<(), String> {
    use tauri::Manager;
    let root = project_root()?;

    // Write .env from wizard config (if present) before spawning Python
    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let cfg_path = config::config_path(&data_dir);
    if let Some(cfg) = config::load_from_path(&cfg_path)? {
        if cfg.setup_complete {
            config::write_env_to_path(&root.join(".env"), &cfg)?;
        }
    }

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
```

- [ ] **Step 3: Register new commands in invoke_handler**

Find `.invoke_handler(tauri::generate_handler![start_bot, stop_bot, get_status, open_dashboard])` and replace with:

```rust
.invoke_handler(tauri::generate_handler![
    start_bot, stop_bot, get_status, open_dashboard,
    load_config, save_config, test_t212_connection, test_ai_connection
])
```

- [ ] **Step 4: Compile check**

```bash
cargo check --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: no errors.

- [ ] **Step 5: Run all Rust tests to confirm nothing broke**

```bash
cargo test --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add desktop-app/src-tauri/src/main.rs
git commit -m "feat: wire load/save/test commands and extend start_bot to write .env"
```

---

### Task 7: TypeScript Config type

**Files:**
- Create: `desktop-app/src/types/config.ts`

- [ ] **Step 1: Create the Config interface**

Create `desktop-app/src/types/config.ts`:

```typescript
export interface Config {
  setup_complete: boolean;
  setup_step: number;
  t212_api_key: string;
  t212_api_secret: string;
  t212_env: "demo" | "live";
  t212_account_type: "invest" | "cfd";
  ai_provider: "anthropic" | "openai" | "azure" | "gemini" | "deepseek" | "ollama";
  ai_api_key: string;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_open_positions: number;
  max_position_size_pct: number;
  watchlist: string[];
}

export const DEFAULT_CONFIG: Config = {
  setup_complete: false,
  setup_step: 0,
  t212_api_key: "",
  t212_api_secret: "",
  t212_env: "demo",
  t212_account_type: "invest",
  ai_provider: "anthropic",
  ai_api_key: "",
  stop_loss_pct: 0.02,
  take_profit_pct: 0.04,
  max_open_positions: 10,
  max_position_size_pct: 0.05,
  watchlist: ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"],
};

export const AI_PROVIDERS: { value: Config["ai_provider"]; label: string; keyLabel: string; keyPlaceholder: string }[] = [
  { value: "anthropic", label: "Anthropic (Claude)", keyLabel: "Anthropic API Key", keyPlaceholder: "sk-ant-api03-..." },
  { value: "openai",    label: "OpenAI",             keyLabel: "OpenAI API Key",    keyPlaceholder: "sk-proj-..."     },
  { value: "azure",     label: "Azure AI",           keyLabel: "Azure AI Key",      keyPlaceholder: "your-azure-key" },
  { value: "gemini",    label: "Google Gemini",      keyLabel: "Gemini API Key",    keyPlaceholder: "AIza..."         },
  { value: "deepseek",  label: "DeepSeek",           keyLabel: "DeepSeek API Key",  keyPlaceholder: "sk-..."          },
  { value: "ollama",    label: "Ollama (local)",     keyLabel: "Ollama Base URL",   keyPlaceholder: "http://localhost:11434" },
];
```

- [ ] **Step 2: Commit**

```bash
git add desktop-app/src/types/config.ts
git commit -m "feat: add TypeScript Config type and AI_PROVIDERS constant"
```

---

### Task 8: Wizard CSS styles

**Files:**
- Modify: `desktop-app/src/styles.css`

- [ ] **Step 1: Append wizard and settings styles**

Append the following to the end of `desktop-app/src/styles.css`:

```css
/* ── Wizard ─────────────────────────────────────────────────── */

.wizard {
  max-width: 560px;
  margin: 0 auto;
  padding: 32px 24px;
}

.wizard-progress {
  margin-bottom: 28px;
}

.wizard-progress-label {
  font-size: 0.8rem;
  color: #9fb2c7;
  margin-bottom: 6px;
}

.wizard-progress-bar {
  height: 4px;
  background: #2b3a50;
  border-radius: 2px;
  overflow: hidden;
}

.wizard-progress-fill {
  height: 100%;
  background: #1E5BFF;
  border-radius: 2px;
  transition: width 220ms cubic-bezier(.2,.8,.2,1);
}

.wizard-step {
  animation: fadeIn 220ms cubic-bezier(.2,.8,.2,1);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.wizard-step h2 {
  margin: 0 0 6px;
  font-size: 1.5rem;
  font-weight: 700;
}

.wizard-step .subtitle {
  color: #9fb2c7;
  margin: 0 0 24px;
  line-height: 1.5;
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: #c9d7e8;
  margin-bottom: 6px;
}

.field input[type="text"],
.field input[type="password"],
.field input[type="number"],
.field select {
  width: 100%;
  background: #111b28;
  border: 1px solid #2b3a50;
  border-radius: 8px;
  color: #e6edf3;
  font-size: 0.95rem;
  padding: 10px 12px;
  outline: none;
  transition: border-color 120ms;
  box-sizing: border-box;
}

.field input:focus,
.field select:focus {
  border-color: #1E5BFF;
}

.field .hint {
  font-size: 0.78rem;
  color: #9fb2c7;
  margin-top: 4px;
}

.toggle-group {
  display: flex;
  gap: 8px;
}

.toggle-group button {
  flex: 1;
  background: #111b28;
  border: 1px solid #2b3a50;
  color: #9fb2c7;
  border-radius: 8px;
  padding: 9px 12px;
  font-weight: 500;
  transition: all 120ms;
}

.toggle-group button.active {
  background: #1E5BFF;
  border-color: #1E5BFF;
  color: #fff;
  font-weight: 700;
}

.toggle-group button.amber {
  border-color: #B8730E;
  color: #f0a050;
}

.toggle-group button.amber.active {
  background: #7a4a0a;
  border-color: #B8730E;
  color: #f0a050;
}

.test-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 4px;
}

.test-row button {
  flex-shrink: 0;
  background: #1E5BFF;
  padding: 9px 18px;
}

.test-result {
  font-size: 0.85rem;
  line-height: 1.4;
  flex: 1;
}

.test-result.ok    { color: #42d392; }
.test-result.error { color: #ff7373; }
.test-result.busy  { color: #9fb2c7; }

.slider-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.slider-row input[type="range"] {
  flex: 1;
  accent-color: #1E5BFF;
}

.slider-row input[type="number"] {
  width: 72px;
  background: #111b28;
  border: 1px solid #2b3a50;
  border-radius: 8px;
  color: #e6edf3;
  font-size: 0.9rem;
  padding: 6px 8px;
  text-align: center;
}

.stepper-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.stepper-row button {
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 6px;
  font-size: 1.2rem;
  line-height: 1;
}

.stepper-value {
  min-width: 40px;
  text-align: center;
  font-size: 1rem;
  font-weight: 700;
}

.watchlist-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.ticker-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #111b28;
  border: 1px solid #2b3a50;
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 0.85rem;
  font-family: "JetBrains Mono", monospace;
  cursor: pointer;
  transition: all 120ms;
  color: #9fb2c7;
}

.ticker-chip.selected {
  border-color: #1E5BFF;
  color: #e6edf3;
  background: rgba(30,91,255,0.12);
}

.ticker-chip .remove {
  font-size: 0.9rem;
  opacity: 0.6;
  cursor: pointer;
  background: none;
  border: none;
  color: inherit;
  padding: 0;
  line-height: 1;
}

.wizard-nav {
  display: flex;
  justify-content: space-between;
  margin-top: 28px;
  gap: 10px;
}

.btn-primary {
  background: #1E5BFF;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 11px 28px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  transition: filter 120ms;
}

.btn-primary:hover:not(:disabled) { filter: brightness(1.12); }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-secondary {
  background: transparent;
  color: #9fb2c7;
  border: 1px solid #2b3a50;
  border-radius: 8px;
  padding: 11px 20px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: border-color 120ms;
}

.btn-secondary:hover { border-color: #1E5BFF; color: #e6edf3; }

.done-screen {
  text-align: center;
  padding: 40px 24px;
}

.done-screen .check {
  font-size: 3rem;
  margin-bottom: 16px;
}

.done-screen h2 {
  margin: 0 0 8px;
  font-size: 1.6rem;
}

.done-screen p {
  color: #9fb2c7;
}

/* ── Settings Panel ──────────────────────────────────────────── */

.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  animation: fadeIn 120ms;
}

.settings-modal {
  background: #131c28;
  border: 1px solid #2b3a50;
  border-radius: 14px;
  width: 90%;
  max-width: 520px;
  max-height: 88vh;
  overflow-y: auto;
  padding: 28px;
}

.settings-modal h2 {
  margin: 0 0 20px;
  font-size: 1.25rem;
}

.settings-section {
  border-top: 1px solid #2b3a50;
  margin-top: 20px;
  padding-top: 20px;
}

.settings-section h3 {
  margin: 0 0 14px;
  font-size: 0.95rem;
  color: #9fb2c7;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
  border-top: 1px solid #2b3a50;
  padding-top: 18px;
}

/* ── Gear icon in launcher ───────────────────────────────────── */

.launcher-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gear-btn {
  background: transparent;
  border: 1px solid #2b3a50;
  border-radius: 8px;
  color: #9fb2c7;
  padding: 6px 10px;
  font-size: 1.1rem;
  cursor: pointer;
  line-height: 1;
  transition: border-color 120ms;
}

.gear-btn:hover { border-color: #1E5BFF; color: #e6edf3; }
```

- [ ] **Step 2: Commit**

```bash
git add desktop-app/src/styles.css
git commit -m "feat: add wizard and settings CSS styles"
```

---

### Task 9: WizardProgress + StepWelcome

**Files:**
- Create: `desktop-app/src/components/wizard/WizardProgress.tsx`
- Create: `desktop-app/src/components/wizard/StepWelcome.tsx`

- [ ] **Step 1: Create WizardProgress.tsx**

Create `desktop-app/src/components/wizard/WizardProgress.tsx`:

```tsx
interface Props {
  current: number;
  total: number;
}

export default function WizardProgress({ current, total }: Props) {
  const pct = Math.round((current / total) * 100);
  return (
    <div className="wizard-progress">
      <div className="wizard-progress-label">Step {current} of {total}</div>
      <div className="wizard-progress-bar">
        <div className="wizard-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create StepWelcome.tsx**

Create `desktop-app/src/components/wizard/StepWelcome.tsx`:

```tsx
interface Props {
  onNext: () => void;
}

export default function StepWelcome({ onNext }: Props) {
  return (
    <div className="wizard-step">
      <h2>Welcome to Claude Trade Bot</h2>
      <p className="subtitle">
        Let's get your trading bot set up. We'll walk you through connecting
        your Trading 212 account, choosing an AI provider, and setting your
        risk limits. Takes about 5 minutes.
      </p>
      <div className="wizard-nav">
        <span />
        <button className="btn-primary" onClick={onNext}>Get Started →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add desktop-app/src/components/wizard/WizardProgress.tsx desktop-app/src/components/wizard/StepWelcome.tsx
git commit -m "feat: add WizardProgress and StepWelcome components"
```

---

### Task 10: StepT212 component + test

**Files:**
- Create: `desktop-app/src/components/wizard/StepT212.tsx`
- Create: `desktop-app/src/__tests__/StepT212.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/StepT212.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import StepT212 from "../components/wizard/StepT212";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

test("Next button disabled until test passes", () => {
  render(<StepT212 {...baseProps} />);
  expect(screen.getByText("Next →")).toBeDisabled();
});

test("Test Connection calls invoke and shows success", async () => {
  mockInvoke.mockResolvedValueOnce("Connected — cash balance: 1234.56");
  render(<StepT212 {...baseProps} />);
  fireEvent.change(screen.getByPlaceholderText(/paste from/i), { target: { value: "mykey" } });
  fireEvent.change(screen.getByPlaceholderText(/secret/i), { target: { value: "mysecret" } });
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Connected/));
  expect(screen.getByText("Next →")).not.toBeDisabled();
});

test("Test Connection shows error message on failure", async () => {
  mockInvoke.mockRejectedValueOnce("Invalid API key or secret");
  render(<StepT212 {...baseProps} />);
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Invalid API key/));
  expect(screen.getByText("Next →")).toBeDisabled();
});
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepT212.test.tsx 2>&1 | tail -10
```

Expected: FAIL — `StepT212` not found.

- [ ] **Step 3: Create StepT212.tsx**

Create `desktop-app/src/components/wizard/StepT212.tsx`:

```tsx
import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onNext: () => void;
  onBack: () => void;
}

type TestState = "idle" | "testing" | "ok" | "error";

export default function StepT212({ config, setConfig, onNext, onBack }: Props) {
  const [key, setKey]       = useState(config.t212_api_key);
  const [secret, setSecret] = useState(config.t212_api_secret);
  const [env, setEnv]       = useState<Config["t212_env"]>(config.t212_env);
  const [acct, setAcct]     = useState<Config["t212_account_type"]>(config.t212_account_type);
  const [test, setTest]     = useState<TestState>("idle");
  const [msg, setMsg]       = useState("");

  async function handleTest() {
    setTest("testing");
    setMsg("Testing connection…");
    try {
      const result = await invoke<string>("test_t212_connection", { key: key.trim(), secret: secret.trim(), env });
      setMsg(result);
      setTest("ok");
      setConfig({ ...config, t212_api_key: key.trim(), t212_api_secret: secret.trim(), t212_env: env, t212_account_type: acct });
    } catch (err) {
      setMsg(String(err));
      setTest("error");
    }
  }

  function handleNext() {
    setConfig({ ...config, t212_api_key: key.trim(), t212_api_secret: secret.trim(), t212_env: env, t212_account_type: acct });
    onNext();
  }

  return (
    <div className="wizard-step">
      <WizardProgress current={2} total={5} />
      <h2>Connect Trading 212</h2>
      <p className="subtitle">Enter your Trading 212 API credentials. Find them in the T212 app under Settings → API.</p>

      <div className="field">
        <label>API Key</label>
        <input type="password" value={key} onChange={e => { setKey(e.target.value); setTest("idle"); }}
          placeholder="Paste from Settings → API in the T212 app" />
      </div>

      <div className="field">
        <label>API Secret</label>
        <input type="password" value={secret} onChange={e => { setSecret(e.target.value); setTest("idle"); }}
          placeholder="Secret from Settings → API" />
      </div>

      <div className="field">
        <label>Mode</label>
        <div className="toggle-group">
          <button className={env === "demo" ? "active" : ""} onClick={() => setEnv("demo")}>Demo (paper money)</button>
          <button className={`${env === "live" ? "active amber" : "amber"}`} onClick={() => setEnv("live")}>Live (real money)</button>
        </div>
        {env === "live" && <div className="hint" style={{ color: "#f0a050" }}>⚠ Live mode uses real funds. Start with Demo.</div>}
      </div>

      <div className="field">
        <label>Account Type</label>
        <div className="toggle-group">
          <button className={acct === "invest" ? "active" : ""} onClick={() => setAcct("invest")}>Invest / ISA</button>
          <button className={acct === "cfd" ? "active" : ""} onClick={() => setAcct("cfd")}>CFD</button>
        </div>
      </div>

      <div className="test-row">
        <button className="btn-primary" onClick={handleTest} disabled={test === "testing" || !key || !secret}>
          {test === "testing" ? "Testing…" : "Test Connection"}
        </button>
        {msg && <span className={`test-result ${test === "ok" ? "ok" : test === "error" ? "error" : "busy"}`}>{msg}</span>}
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleNext} disabled={test !== "ok"}>Next →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepT212.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src/components/wizard/StepT212.tsx desktop-app/src/__tests__/StepT212.test.tsx
git commit -m "feat: add StepT212 component with connection test and Vitest tests"
```

---

### Task 11: StepAIProvider component + test

**Files:**
- Create: `desktop-app/src/components/wizard/StepAIProvider.tsx`
- Create: `desktop-app/src/__tests__/StepAIProvider.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/StepAIProvider.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import StepAIProvider from "../components/wizard/StepAIProvider";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("Next disabled until test passes", () => {
  render(<StepAIProvider {...baseProps} />);
  expect(screen.getByText("Next →")).toBeDisabled();
});

test("provider selector updates key label", () => {
  render(<StepAIProvider {...baseProps} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "openai" } });
  expect(screen.getByText("OpenAI API Key")).toBeInTheDocument();
});

test("successful test enables Next", async () => {
  mockInvoke.mockResolvedValueOnce("Connected — Anthropic API");
  render(<StepAIProvider {...baseProps} />);
  fireEvent.change(screen.getByPlaceholderText(/sk-ant/i), { target: { value: "sk-ant-xxx" } });
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Connected/));
  expect(screen.getByText("Next →")).not.toBeDisabled();
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepAIProvider.test.tsx 2>&1 | tail -6
```

Expected: FAIL — `StepAIProvider` not found.

- [ ] **Step 3: Create StepAIProvider.tsx**

Create `desktop-app/src/components/wizard/StepAIProvider.tsx`:

```tsx
import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config, AI_PROVIDERS } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onNext: () => void;
  onBack: () => void;
}

type TestState = "idle" | "testing" | "ok" | "error";

export default function StepAIProvider({ config, setConfig, onNext, onBack }: Props) {
  const [provider, setProvider] = useState<Config["ai_provider"]>(config.ai_provider);
  const [key, setKey]           = useState(config.ai_api_key);
  const [test, setTest]         = useState<TestState>("idle");
  const [msg, setMsg]           = useState("");

  const meta = AI_PROVIDERS.find(p => p.value === provider) ?? AI_PROVIDERS[0];

  async function handleTest() {
    setTest("testing");
    setMsg("Testing connection…");
    try {
      const result = await invoke<string>("test_ai_connection", { provider, key: key.trim() });
      setMsg(result);
      setTest("ok");
      setConfig({ ...config, ai_provider: provider, ai_api_key: key.trim() });
    } catch (err) {
      setMsg(String(err));
      setTest("error");
    }
  }

  function handleNext() {
    setConfig({ ...config, ai_provider: provider, ai_api_key: key.trim() });
    onNext();
  }

  return (
    <div className="wizard-step">
      <WizardProgress current={3} total={5} />
      <h2>AI Provider</h2>
      <p className="subtitle">Choose the AI model that will generate trade signals. Anthropic (Claude) is recommended.</p>

      <div className="field">
        <label>Provider</label>
        <select value={provider} onChange={e => { setProvider(e.target.value as Config["ai_provider"]); setTest("idle"); setMsg(""); }}>
          {AI_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </div>

      <div className="field">
        <label>{meta.keyLabel}</label>
        <input type="password" value={key}
          onChange={e => { setKey(e.target.value); setTest("idle"); }}
          placeholder={meta.keyPlaceholder}
        />
      </div>

      <div className="test-row">
        <button className="btn-primary" onClick={handleTest}
          disabled={test === "testing" || (provider !== "ollama" && !key)}>
          {test === "testing" ? "Testing…" : "Test Connection"}
        </button>
        {msg && <span className={`test-result ${test === "ok" ? "ok" : test === "error" ? "error" : "busy"}`}>{msg}</span>}
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleNext} disabled={test !== "ok"}>Next →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepAIProvider.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src/components/wizard/StepAIProvider.tsx desktop-app/src/__tests__/StepAIProvider.test.tsx
git commit -m "feat: add StepAIProvider component with connection test and Vitest tests"
```

---

### Task 12: StepRiskProfile component + test

**Files:**
- Create: `desktop-app/src/components/wizard/StepRiskProfile.tsx`
- Create: `desktop-app/src/__tests__/StepRiskProfile.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/StepRiskProfile.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import StepRiskProfile from "../components/wizard/StepRiskProfile";
import { DEFAULT_CONFIG } from "../types/config";

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("renders default values", () => {
  render(<StepRiskProfile {...baseProps} />);
  expect(screen.getByDisplayValue("2")).toBeInTheDocument(); // stop-loss 2%
  expect(screen.getByDisplayValue("4")).toBeInTheDocument(); // take-profit 4%
});

test("Next always enabled on this step", () => {
  render(<StepRiskProfile {...baseProps} />);
  expect(screen.getByText("Next →")).not.toBeDisabled();
});

test("clicking Next calls onNext", () => {
  render(<StepRiskProfile {...baseProps} />);
  fireEvent.click(screen.getByText("Next →"));
  expect(baseProps.onNext).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepRiskProfile.test.tsx 2>&1 | tail -6
```

Expected: FAIL.

- [ ] **Step 3: Create StepRiskProfile.tsx**

Create `desktop-app/src/components/wizard/StepRiskProfile.tsx`:

```tsx
import { useState } from "react";
import { Config } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onNext: () => void;
  onBack: () => void;
}

export default function StepRiskProfile({ config, setConfig, onNext, onBack }: Props) {
  const [stopLoss,  setStopLoss]  = useState(+(config.stop_loss_pct  * 100).toFixed(1));
  const [takeProfit,setTakeProfit]= useState(+(config.take_profit_pct * 100).toFixed(1));
  const [maxPos,    setMaxPos]    = useState(config.max_open_positions);
  const [maxSize,   setMaxSize]   = useState(+(config.max_position_size_pct * 100).toFixed(1));

  function handleNext() {
    setConfig({
      ...config,
      stop_loss_pct:        stopLoss  / 100,
      take_profit_pct:      takeProfit / 100,
      max_open_positions:   maxPos,
      max_position_size_pct: maxSize  / 100,
    });
    onNext();
  }

  return (
    <div className="wizard-step">
      <WizardProgress current={4} total={5} />
      <h2>Risk Profile</h2>
      <p className="subtitle">These limits control how aggressively the bot trades. The defaults are conservative — great for getting started.</p>

      <div className="field">
        <label>Stop-Loss ({stopLoss}%)</label>
        <div className="slider-row">
          <input type="range" min={0.5} max={10} step={0.5} value={stopLoss}
            onChange={e => setStopLoss(+e.target.value)} />
          <input type="number" min={0.5} max={10} step={0.5} value={stopLoss}
            onChange={e => setStopLoss(+e.target.value)} />
        </div>
        <div className="hint">Close a position when it falls this % below the purchase price.</div>
      </div>

      <div className="field">
        <label>Take-Profit ({takeProfit}%)</label>
        <div className="slider-row">
          <input type="range" min={1} max={20} step={0.5} value={takeProfit}
            onChange={e => setTakeProfit(+e.target.value)} />
          <input type="number" min={1} max={20} step={0.5} value={takeProfit}
            onChange={e => setTakeProfit(+e.target.value)} />
        </div>
        <div className="hint">Close a position when it gains this % above the purchase price.</div>
      </div>

      <div className="field">
        <label>Max Open Positions</label>
        <div className="stepper-row">
          <button onClick={() => setMaxPos(Math.max(1, maxPos - 1))}>−</button>
          <span className="stepper-value">{maxPos}</span>
          <button onClick={() => setMaxPos(Math.min(50, maxPos + 1))}>+</button>
        </div>
        <div className="hint">Maximum number of stocks held at any one time.</div>
      </div>

      <div className="field">
        <label>Max Position Size ({maxSize}% of portfolio)</label>
        <div className="slider-row">
          <input type="range" min={1} max={20} step={0.5} value={maxSize}
            onChange={e => setMaxSize(+e.target.value)} />
          <input type="number" min={1} max={20} step={0.5} value={maxSize}
            onChange={e => setMaxSize(+e.target.value)} />
        </div>
        <div className="hint">No single trade will exceed this % of your total portfolio value.</div>
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleNext}>Next →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepRiskProfile.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src/components/wizard/StepRiskProfile.tsx desktop-app/src/__tests__/StepRiskProfile.test.tsx
git commit -m "feat: add StepRiskProfile component with sliders and Vitest tests"
```

---

### Task 13: StepWatchlist component + test

**Files:**
- Create: `desktop-app/src/components/wizard/StepWatchlist.tsx`
- Create: `desktop-app/src/__tests__/StepWatchlist.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/StepWatchlist.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import StepWatchlist from "../components/wizard/StepWatchlist";
import { DEFAULT_CONFIG } from "../types/config";

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onFinish: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("renders default tickers", () => {
  render(<StepWatchlist {...baseProps} />);
  expect(screen.getByText("AAPL")).toBeInTheDocument();
  expect(screen.getByText("TSLA")).toBeInTheDocument();
});

test("Finish disabled when watchlist is empty", () => {
  const config = { ...DEFAULT_CONFIG, watchlist: [] };
  render(<StepWatchlist {...baseProps} config={config} />);
  expect(screen.getByText("Finish Setup")).toBeDisabled();
});

test("typing and pressing Enter adds a ticker", () => {
  render(<StepWatchlist {...baseProps} />);
  const input = screen.getByPlaceholderText(/add ticker/i);
  fireEvent.change(input, { target: { value: "HOOD" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByText("HOOD")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepWatchlist.test.tsx 2>&1 | tail -6
```

Expected: FAIL.

- [ ] **Step 3: Create StepWatchlist.tsx**

Create `desktop-app/src/components/wizard/StepWatchlist.tsx`:

```tsx
import { useState } from "react";
import { Config } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onFinish: () => void;
  onBack: () => void;
}

export default function StepWatchlist({ config, setConfig, onFinish, onBack }: Props) {
  const [tickers, setTickers] = useState<string[]>(config.watchlist);
  const [input, setInput]     = useState("");

  function toggle(ticker: string) {
    setTickers(prev =>
      prev.includes(ticker) ? prev.filter(t => t !== ticker) : [...prev, ticker]
    );
  }

  function addTicker() {
    const t = input.trim().toUpperCase();
    if (t && !tickers.includes(t)) {
      setTickers(prev => [...prev, t]);
    }
    setInput("");
  }

  function removeTicker(ticker: string) {
    setTickers(prev => prev.filter(t => t !== ticker));
  }

  function handleFinish() {
    setConfig({ ...config, watchlist: tickers });
    onFinish();
  }

  const defaults = ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"];
  const extras   = tickers.filter(t => !defaults.includes(t));

  return (
    <div className="wizard-step">
      <WizardProgress current={5} total={5} />
      <h2>Watchlist</h2>
      <p className="subtitle">Choose the stocks the bot will monitor and trade. You can change this at any time in Settings.</p>

      <div className="watchlist-grid">
        {defaults.map(t => (
          <span key={t} className={`ticker-chip ${tickers.includes(t) ? "selected" : ""}`} onClick={() => toggle(t)}>
            {tickers.includes(t) ? "✓ " : ""}{t}
          </span>
        ))}
        {extras.map(t => (
          <span key={t} className="ticker-chip selected">
            {t}
            <button className="remove" onClick={() => removeTicker(t)}>×</button>
          </span>
        ))}
      </div>

      <div className="field">
        <label>Add a ticker</label>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && addTicker()}
          placeholder="Add ticker (e.g. SHOP) and press Enter"
        />
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleFinish} disabled={tickers.length === 0}>Finish Setup</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/StepWatchlist.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src/components/wizard/StepWatchlist.tsx desktop-app/src/__tests__/StepWatchlist.test.tsx
git commit -m "feat: add StepWatchlist component with chip UI and Vitest tests"
```

---

### Task 14: StepDone component

**Files:**
- Create: `desktop-app/src/components/wizard/StepDone.tsx`

- [ ] **Step 1: Create StepDone.tsx**

Create `desktop-app/src/components/wizard/StepDone.tsx`:

```tsx
import { useEffect } from "react";

interface Props {
  onComplete: () => void;
}

export default function StepDone({ onComplete }: Props) {
  useEffect(() => {
    const timer = setTimeout(onComplete, 2000);
    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <div className="wizard-step done-screen">
      <div className="check">✓</div>
      <h2>You're all set!</h2>
      <p>Your bot is configured and ready to trade. Starting the launcher…</p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add desktop-app/src/components/wizard/StepDone.tsx
git commit -m "feat: add StepDone component with 2s auto-transition"
```

---

### Task 15: SetupWizard container + test

**Files:**
- Create: `desktop-app/src/components/wizard/SetupWizard.tsx`
- Create: `desktop-app/src/__tests__/SetupWizard.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/SetupWizard.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import SetupWizard from "../components/wizard/SetupWizard";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

beforeEach(() => {
  vi.clearAllMocks();
  mockInvoke.mockResolvedValue(undefined); // save_config succeeds
});

test("starts on welcome screen", () => {
  render(<SetupWizard initialConfig={DEFAULT_CONFIG} onComplete={vi.fn()} />);
  expect(screen.getByText("Welcome to Claude Trade Bot")).toBeInTheDocument();
});

test("Get Started advances to Step 2", () => {
  render(<SetupWizard initialConfig={DEFAULT_CONFIG} onComplete={vi.fn()} />);
  fireEvent.click(screen.getByText("Get Started →"));
  expect(screen.getByText("Connect Trading 212")).toBeInTheDocument();
});

test("resumes from setup_step if setup_complete is false", () => {
  const partial = { ...DEFAULT_CONFIG, setup_step: 2, setup_complete: false };
  render(<SetupWizard initialConfig={partial} onComplete={vi.fn()} />);
  // setup_step: 2 = AI Provider was last saved; resumeStep = 2+1 = 3 = Risk Profile
  expect(screen.getByText("Risk Profile")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd desktop-app && pnpm vitest run src/__tests__/SetupWizard.test.tsx 2>&1 | tail -6
```

Expected: FAIL.

- [ ] **Step 3: Create SetupWizard.tsx**

Create `desktop-app/src/components/wizard/SetupWizard.tsx`:

```tsx
import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config } from "../../types/config";
import StepWelcome     from "./StepWelcome";
import StepT212        from "./StepT212";
import StepAIProvider  from "./StepAIProvider";
import StepRiskProfile from "./StepRiskProfile";
import StepWatchlist   from "./StepWatchlist";
import StepDone        from "./StepDone";

interface Props {
  initialConfig: Config;
  onComplete: () => void;
}

export default function SetupWizard({ initialConfig, onComplete }: Props) {
  // Resume: if setup_step > 0, start at the next incomplete step (setup_step + 1)
  const resumeStep = initialConfig.setup_complete ? 0 : Math.min(initialConfig.setup_step + 1, 5);
  const [step, setStep]     = useState(resumeStep);
  const [config, setConfig] = useState<Config>(initialConfig);

  async function advance() {
    const next = step + 1;
    const partial: Config = { ...config, setup_step: step, setup_complete: false };
    await invoke("save_config", { config: partial }).catch(() => {});
    setStep(next);
  }

  async function finish() {
    const final: Config = { ...config, setup_step: 5, setup_complete: true };
    await invoke("save_config", { config: final }).catch(() => {});
    setConfig(final);
    setStep(6);
  }

  return (
    <div className="wizard">
      {step === 0 && <StepWelcome onNext={advance} />}
      {step === 1 && <StepT212        config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(0)} />}
      {step === 2 && <StepAIProvider  config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(1)} />}
      {step === 3 && <StepRiskProfile config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(2)} />}
      {step === 4 && <StepWatchlist   config={config} setConfig={setConfig} onFinish={finish} onBack={() => setStep(3)} />}
      {step >= 5  && <StepDone onComplete={onComplete} />}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/SetupWizard.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add desktop-app/src/components/wizard/SetupWizard.tsx desktop-app/src/__tests__/SetupWizard.test.tsx
git commit -m "feat: add SetupWizard container with resume support and Vitest tests"
```

---

### Task 16: SettingsPanel component + test

**Files:**
- Create: `desktop-app/src/components/SettingsPanel.tsx`
- Create: `desktop-app/src/__tests__/SettingsPanel.test.tsx`

- [ ] **Step 1: Write failing test**

Create `desktop-app/src/__tests__/SettingsPanel.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import SettingsPanel from "../components/SettingsPanel";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG, t212_api_key: "key123", setup_complete: true },
  onSave: vi.fn(),
  onClose: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  mockInvoke.mockResolvedValue(undefined);
});

test("renders with pre-populated T212 key", () => {
  render(<SettingsPanel {...baseProps} />);
  expect(screen.getByDisplayValue("key123")).toBeInTheDocument();
});

test("Save calls invoke save_config and onSave", async () => {
  render(<SettingsPanel {...baseProps} />);
  fireEvent.click(screen.getByText("Save Settings"));
  await waitFor(() => expect(mockInvoke).toHaveBeenCalledWith("save_config", expect.anything()));
  expect(baseProps.onSave).toHaveBeenCalled();
});

test("Cancel calls onClose without saving", () => {
  render(<SettingsPanel {...baseProps} />);
  fireEvent.click(screen.getByText("Cancel"));
  expect(baseProps.onClose).toHaveBeenCalled();
  expect(mockInvoke).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd desktop-app && pnpm vitest run src/__tests__/SettingsPanel.test.tsx 2>&1 | tail -6
```

Expected: FAIL.

- [ ] **Step 3: Create SettingsPanel.tsx**

Create `desktop-app/src/components/SettingsPanel.tsx`:

```tsx
import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config, AI_PROVIDERS } from "../types/config";

interface Props {
  config: Config;
  onSave: (updated: Config) => void;
  onClose: () => void;
}

export default function SettingsPanel({ config, onSave, onClose }: Props) {
  const [t212Key,    setT212Key]    = useState(config.t212_api_key);
  const [t212Secret, setT212Secret] = useState(config.t212_api_secret);
  const [env,        setEnv]        = useState<Config["t212_env"]>(config.t212_env);
  const [acct,       setAcct]       = useState<Config["t212_account_type"]>(config.t212_account_type);
  const [provider,   setProvider]   = useState<Config["ai_provider"]>(config.ai_provider);
  const [aiKey,      setAiKey]      = useState(config.ai_api_key);
  const [stopLoss,   setStopLoss]   = useState(+(config.stop_loss_pct * 100).toFixed(1));
  const [takeProfit, setTakeProfit] = useState(+(config.take_profit_pct * 100).toFixed(1));
  const [maxPos,     setMaxPos]     = useState(config.max_open_positions);
  const [maxSize,    setMaxSize]    = useState(+(config.max_position_size_pct * 100).toFixed(1));
  const [watchlist,  setWatchlist]  = useState(config.watchlist.join(", "));
  const [saving,     setSaving]     = useState(false);

  const meta = AI_PROVIDERS.find(p => p.value === provider) ?? AI_PROVIDERS[0];

  async function handleSave() {
    setSaving(true);
    const updated: Config = {
      ...config,
      t212_api_key:          t212Key.trim(),
      t212_api_secret:       t212Secret.trim(),
      t212_env:              env,
      t212_account_type:     acct,
      ai_provider:           provider,
      ai_api_key:            aiKey.trim(),
      stop_loss_pct:         stopLoss / 100,
      take_profit_pct:       takeProfit / 100,
      max_open_positions:    maxPos,
      max_position_size_pct: maxSize / 100,
      watchlist:             watchlist.split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
    };
    await invoke("save_config", { config: updated });
    setSaving(false);
    onSave(updated);
  }

  return (
    <div className="settings-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="settings-modal">
        <h2>⚙ Settings</h2>

        <div className="settings-section">
          <h3>Trading 212</h3>
          <div className="field">
            <label>API Key</label>
            <input type="password" value={t212Key} onChange={e => setT212Key(e.target.value)} />
          </div>
          <div className="field">
            <label>API Secret</label>
            <input type="password" value={t212Secret} onChange={e => setT212Secret(e.target.value)} />
          </div>
          <div className="field">
            <label>Mode</label>
            <div className="toggle-group">
              <button className={env === "demo" ? "active" : ""} onClick={() => setEnv("demo")}>Demo</button>
              <button className={`${env === "live" ? "active amber" : "amber"}`} onClick={() => setEnv("live")}>Live</button>
            </div>
          </div>
          <div className="field">
            <label>Account Type</label>
            <div className="toggle-group">
              <button className={acct === "invest" ? "active" : ""} onClick={() => setAcct("invest")}>Invest / ISA</button>
              <button className={acct === "cfd" ? "active" : ""} onClick={() => setAcct("cfd")}>CFD</button>
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h3>AI Provider</h3>
          <div className="field">
            <label>Provider</label>
            <select value={provider} onChange={e => setProvider(e.target.value as Config["ai_provider"])}>
              {AI_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>{meta.keyLabel}</label>
            <input type="password" value={aiKey} onChange={e => setAiKey(e.target.value)} placeholder={meta.keyPlaceholder} />
          </div>
        </div>

        <div className="settings-section">
          <h3>Risk Profile</h3>
          <div className="field">
            <label>Stop-Loss ({stopLoss}%)</label>
            <div className="slider-row">
              <input type="range" min={0.5} max={10} step={0.5} value={stopLoss} onChange={e => setStopLoss(+e.target.value)} />
              <input type="number" min={0.5} max={10} step={0.5} value={stopLoss} onChange={e => setStopLoss(+e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Take-Profit ({takeProfit}%)</label>
            <div className="slider-row">
              <input type="range" min={1} max={20} step={0.5} value={takeProfit} onChange={e => setTakeProfit(+e.target.value)} />
              <input type="number" min={1} max={20} step={0.5} value={takeProfit} onChange={e => setTakeProfit(+e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Max Open Positions</label>
            <div className="stepper-row">
              <button onClick={() => setMaxPos(Math.max(1, maxPos - 1))}>−</button>
              <span className="stepper-value">{maxPos}</span>
              <button onClick={() => setMaxPos(Math.min(50, maxPos + 1))}>+</button>
            </div>
          </div>
          <div className="field">
            <label>Max Position Size ({maxSize}%)</label>
            <div className="slider-row">
              <input type="range" min={1} max={20} step={0.5} value={maxSize} onChange={e => setMaxSize(+e.target.value)} />
              <input type="number" min={1} max={20} step={0.5} value={maxSize} onChange={e => setMaxSize(+e.target.value)} />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <h3>Watchlist</h3>
          <div className="field">
            <label>Tickers (comma-separated)</label>
            <input type="text" value={watchlist} onChange={e => setWatchlist(e.target.value)} placeholder="AAPL, TSLA, NVDA" />
          </div>
        </div>

        <div className="settings-footer">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests**

```bash
cd desktop-app && pnpm vitest run src/__tests__/SettingsPanel.test.tsx
```

Expected: 3 tests pass.

- [ ] **Step 5: Run all tests to confirm no regressions**

```bash
cd desktop-app && pnpm vitest run
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add desktop-app/src/components/SettingsPanel.tsx desktop-app/src/__tests__/SettingsPanel.test.tsx
git commit -m "feat: add SettingsPanel modal component with Vitest tests"
```

---

### Task 17: Wire App.tsx

**Files:**
- Modify: `desktop-app/src/App.tsx`

- [ ] **Step 1: Replace App.tsx entirely**

Replace the full content of `desktop-app/src/App.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { Config, DEFAULT_CONFIG } from "./types/config";
import SetupWizard from "./components/wizard/SetupWizard";
import SettingsPanel from "./components/SettingsPanel";

type BotKey = "stock" | "prediction";
type BotState = "running" | "stopped";
type StatusMap = Record<BotKey, BotState>;

const DASHBOARD_URLS: Record<BotKey, string> = {
  stock: "http://localhost:4000",
  prediction: "http://localhost:4001",
};

type AppView = "loading" | "wizard" | "launcher";

export default function App() {
  const [view,          setView]          = useState<AppView>("loading");
  const [config,        setConfig]        = useState<Config>(DEFAULT_CONFIG);
  const [showSettings,  setShowSettings]  = useState(false);
  const [status,        setStatus]        = useState<StatusMap>({ stock: "stopped", prediction: "stopped" });
  const [message,       setMessage]       = useState("Ready. Start a bot to continue.");
  const [busy,          setBusy]          = useState(false);
  const tauriMode = isTauri();

  const runningCount = useMemo(
    () => Object.values(status).filter(s => s === "running").length,
    [status]
  );

  // On boot: check for existing config to decide wizard vs launcher
  useEffect(() => {
    if (!tauriMode) { setView("launcher"); return; }
    invoke<Config | null>("load_config")
      .then(cfg => {
        if (cfg && cfg.setup_complete) {
          setConfig(cfg);
          setView("launcher");
        } else {
          setConfig(cfg ?? DEFAULT_CONFIG);
          setView("wizard");
        }
      })
      .catch(() => setView("wizard"));
  }, [tauriMode]);

  function handleWizardComplete() {
    invoke<Config | null>("load_config").then(cfg => {
      if (cfg) setConfig(cfg);
      setView("launcher");
    });
  }

  function handleSettingsSave(updated: Config) {
    setConfig(updated);
    setShowSettings(false);
  }

  async function refreshStatus() {
    if (!tauriMode) {
      setMessage("Desktop controls available only in the Tauri app.");
      return;
    }
    try {
      const next = await invoke<StatusMap>("get_status");
      setStatus(next);
    } catch (err) {
      setMessage(`Could not refresh status: ${String(err)}`);
    }
  }

  async function startBot(bot: BotKey) {
    if (!tauriMode) return;
    setBusy(true);
    try {
      await invoke("start_bot", { bot });
      setMessage(`Started ${bot} bot.`);
      await refreshStatus();
    } catch (err) {
      setMessage(`Could not start ${bot} bot: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function stopBot(bot: BotKey) {
    if (!tauriMode) return;
    setBusy(true);
    try {
      await invoke("stop_bot", { bot });
      setMessage(`Stopped ${bot} bot.`);
      await refreshStatus();
    } catch (err) {
      setMessage(`Could not stop ${bot} bot: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function openDashboard(bot: BotKey) {
    if (!tauriMode) { window.open(DASHBOARD_URLS[bot], "_blank"); return; }
    try {
      await invoke("open_dashboard", { bot });
    } catch (err) {
      setMessage(`Could not open dashboard: ${String(err)}`);
    }
  }

  useEffect(() => {
    refreshStatus();
    const timer = setInterval(refreshStatus, 1500);
    return () => clearInterval(timer);
  }, []);

  if (view === "loading") {
    return <div className="app" style={{ textAlign: "center", paddingTop: 80, color: "#9fb2c7" }}>Loading…</div>;
  }

  if (view === "wizard") {
    return <SetupWizard initialConfig={config} onComplete={handleWizardComplete} />;
  }

  return (
    <main className="app">
      <header className="top launcher-header">
        <div>
          <h1>Claude Trade Bot</h1>
          <p>One-click launcher for stock and prediction dashboards</p>
        </div>
        <button className="gear-btn" onClick={() => setShowSettings(true)} title="Settings">⚙</button>
      </header>

      {showSettings && (
        <SettingsPanel config={config} onSave={handleSettingsSave} onClose={() => setShowSettings(false)} />
      )}

      <section className="summary">
        <div className="card">
          <span className="label">Running Services</span>
          <span className="value">{runningCount}/2</span>
        </div>
        <div className="card">
          <span className="label">Stock Bot</span>
          <span className={`value ${status.stock}`}>{status.stock.toUpperCase()}</span>
        </div>
        <div className="card">
          <span className="label">Prediction Bot</span>
          <span className={`value ${status.prediction}`}>{status.prediction.toUpperCase()}</span>
        </div>
      </section>

      <section className="panel">
        <h2>Stock Bot</h2>
        <div className="actions">
          <button disabled={busy} onClick={() => startBot("stock")}>Start</button>
          <button disabled={busy} onClick={() => stopBot("stock")}>Stop</button>
          <button disabled={busy} onClick={() => openDashboard("stock")}>Open Dashboard</button>
        </div>
      </section>

      <section className="panel">
        <h2>Prediction Bot</h2>
        <div className="actions">
          <button disabled={busy} onClick={() => startBot("prediction")}>Start</button>
          <button disabled={busy} onClick={() => stopBot("prediction")}>Stop</button>
          <button disabled={busy} onClick={() => openDashboard("prediction")}>Open Dashboard</button>
        </div>
      </section>

      <section className="panel">
        <h2>Quick Controls</h2>
        <div className="actions">
          <button disabled={busy} onClick={() => { startBot("stock"); startBot("prediction"); }}>Start All</button>
          <button disabled={busy} onClick={() => { stopBot("stock"); stopBot("prediction"); }}>Stop All</button>
          <button disabled={busy} onClick={refreshStatus}>Refresh Status</button>
        </div>
      </section>

      <footer className="status">
        {message}<br />
        Stock: {DASHBOARD_URLS.stock} | Prediction: {DASHBOARD_URLS.prediction}
      </footer>
      {!tauriMode && (
        <footer className="status">
          Web preview mode — backend controls require the Tauri runtime.
        </footer>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Run all tests**

```bash
cd desktop-app && pnpm vitest run
```

Expected: all tests pass.

- [ ] **Step 3: TypeScript compile check**

```bash
cd desktop-app && pnpm build 2>&1 | tail -10
```

Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add desktop-app/src/App.tsx
git commit -m "feat: wire wizard and settings panel into App.tsx with loading state"
```

---

### Task 18: Self-review + open PR

- [ ] **Step 1: Run full Rust test suite**

```bash
cargo test --manifest-path desktop-app/src-tauri/Cargo.toml
```

Expected: 6 tests pass.

- [ ] **Step 2: Run full React test suite**

```bash
cd desktop-app && pnpm vitest run
```

Expected: all tests pass.

- [ ] **Step 3: TypeScript build**

```bash
cd desktop-app && pnpm build
```

Expected: no errors.

- [ ] **Step 4: Open PR**

```bash
gh pr create \
  --title "feat: first-run onboarding wizard (issue #81)" \
  --body "$(cat <<'EOF'
## Summary
- Adds a 5-step first-run wizard to the Tauri desktop app (T212 keys, AI provider, risk profile, watchlist)
- New Rust commands: `load_config`, `save_config`, `test_t212_connection`, `test_ai_connection`
- Config stored as JSON in OS app-data directory; never inside the repo
- `start_bot` writes an ephemeral `.env` from config before spawning Python (Python side unchanged)
- Settings panel (⚙ gear icon) lets users update config post-setup
- Resume support: wizard saves progress after each step and resumes from `setup_step` on re-open

## Test plan
- [ ] Run `cargo test` — 6 Rust unit tests pass (config round-trip, env generation, key preservation)
- [ ] Run `pnpm vitest run` — React component tests pass (step navigation, disabled Next, resume)
- [ ] Fresh install: delete `~/Library/Application Support/com.claudetradebot.desktop/config.json`, launch app — wizard appears
- [ ] Complete wizard: launcher appears with ⚙ gear icon
- [ ] Gear icon opens settings modal pre-populated with saved values
- [ ] Start Stock Bot: `.env` written to project root with correct keys, Python starts

Closes #81

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

*End of plan.*
