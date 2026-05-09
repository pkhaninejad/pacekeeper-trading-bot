import { useEffect, useMemo, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";

type BotKey = "stock" | "prediction";
type BotState = "running" | "stopped";

type StatusMap = Record<BotKey, BotState>;

const DASHBOARD_URLS: Record<BotKey, string> = {
  stock: "http://localhost:4000",
  prediction: "http://localhost:4001",
};

export default function App() {
  const [status, setStatus] = useState<StatusMap>({ stock: "stopped", prediction: "stopped" });
  const [message, setMessage] = useState("Ready. Start a bot to continue.");
  const [busy, setBusy] = useState(false);
  const tauriMode = isTauri();

  const runningCount = useMemo(
    () => Object.values(status).filter((s) => s === "running").length,
    [status]
  );

  async function refreshStatus() {
    if (!tauriMode) {
      setMessage("Desktop controls are available only in the Tauri app. Start with: pnpm tauri:dev");
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
    if (!tauriMode) {
      window.open(DASHBOARD_URLS[bot], "_blank");
      return;
    }
    try {
      await invoke("open_dashboard", { bot });
      setMessage(`Opened ${bot} dashboard in your browser.`);
    } catch (err) {
      setMessage(`Could not open dashboard: ${String(err)}`);
    }
  }

  async function startAll() {
    await startBot("stock");
    await startBot("prediction");
  }

  async function stopAll() {
    await stopBot("stock");
    await stopBot("prediction");
  }

  useEffect(() => {
    refreshStatus();
    const timer = setInterval(refreshStatus, 1500);
    return () => clearInterval(timer);
  }, []);

  return (
    <main className="app">
      <header className="top">
        <h1>Claude Trade Bot Desktop</h1>
        <p>One-click launcher for stock and prediction dashboards</p>
      </header>

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
          <button disabled={busy} onClick={startAll}>Start All</button>
          <button disabled={busy} onClick={stopAll}>Stop All</button>
          <button disabled={busy} onClick={refreshStatus}>Refresh Status</button>
        </div>
      </section>

      <footer className="status">{message}<br/>Stock: {DASHBOARD_URLS.stock} | Prediction: {DASHBOARD_URLS.prediction}</footer>
      {!tauriMode && (
        <footer className="status">
          You are in web preview mode. Backend start/stop requires Tauri runtime.
        </footer>
      )}
    </main>
  );
}
