import { useEffect, useMemo, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { Config, DEFAULT_CONFIG } from "./types/config";
import SetupWizard from "./components/wizard/SetupWizard";
import SettingsPanel from "./components/SettingsPanel";
import { getVersion } from "@tauri-apps/api/app";
import UpdateBanner from "./components/UpdateBanner";

type BotKey = "stock" | "prediction";
type BotState = "running" | "stopped";
type StatusMap = Record<BotKey, BotState>;

const DASHBOARD_URLS: Record<BotKey, string> = {
  stock: "http://localhost:4000",
  prediction: "http://localhost:4001",
};

type AppView = "loading" | "wizard" | "launcher";

interface LicenseInfo {
  email: string;
  expires?: string;
}

export default function App() {
  const [view,         setView]         = useState<AppView>("loading");
  const [config,       setConfig]       = useState<Config>(DEFAULT_CONFIG);
  const [showSettings, setShowSettings] = useState(false);
  const [status,       setStatus]       = useState<StatusMap>({ stock: "stopped", prediction: "stopped" });
  const [message,      setMessage]      = useState("Ready. Start a bot to continue.");
  const [busy,         setBusy]         = useState(false);
  const [appVersion,   setAppVersion]   = useState<string | null>(null);
  const [license,      setLicense]      = useState<LicenseInfo | null>(null);
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
    invoke<Config | null>("load_config")
      .then(cfg => { if (cfg) setConfig(cfg); })
      .catch(() => {})
      .finally(() => setView("launcher"));
  }

  useEffect(() => {
    if (!tauriMode || view !== "launcher") return;
    invoke<LicenseInfo>("get_license_info").then(setLicense).catch(() => {});
  }, [tauriMode, view]);

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
      setMessage(`Started ${bot} bot — opening dashboard…`);
      await refreshStatus();
      // Give the Python server ~3 s to bind its port before opening the browser
      setTimeout(() => openDashboard(bot), 3000);
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

  useEffect(() => {
    if (tauriMode) {
      getVersion().then(setAppVersion).catch(() => {});
    }
  }, [tauriMode]);

  if (view === "loading") {
    return <div className="app" style={{ textAlign: "center", paddingTop: 80, color: "#9fb2c7" }}>Loading…</div>;
  }

  if (view === "wizard") {
    return <SetupWizard initialConfig={config} onComplete={handleWizardComplete} />;
  }

  return (
    <main className="app">
      <UpdateBanner />
      <header className="top launcher-header">
        <div>
          <h1>Pacekeeper</h1>
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
        {license && (
          <div className="card">
            <span className="label">License</span>
            <span className="value" style={{ fontSize: "0.75rem", color: "var(--sage)" }}>
              {license.email}
            </span>
            {license.expires && (
              <span style={{ fontFamily: "var(--mono)", fontSize: "0.7rem", color: "var(--ink-3)" }}>
                expires {license.expires}
              </span>
            )}
          </div>
        )}
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

      <footer className="status" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{message}</span>
        {appVersion && (
          <span style={{ fontFamily: "var(--mono)", color: "var(--ink-4)", fontSize: "0.8rem" }}>
            v{appVersion}
          </span>
        )}
      </footer>
      {!tauriMode && (
        <footer className="status">
          Web preview mode — backend controls require the Tauri runtime.
        </footer>
      )}
    </main>
  );
}
