import { useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { Config, AI_PROVIDERS, AI_PROVIDER_MODELS, defaultModel } from "../types/config";

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
  const [aiModel,    setAiModel]    = useState(config.ai_model || defaultModel(config.ai_provider));
  const [azureEp,    setAzureEp]    = useState(config.azure_endpoint);
  const [stopLoss,   setStopLoss]   = useState(+(config.stop_loss_pct   * 100).toFixed(1));
  const [takeProfit, setTakeProfit] = useState(+(config.take_profit_pct * 100).toFixed(1));
  const [maxPos,     setMaxPos]     = useState(config.max_open_positions);
  const [maxSize,    setMaxSize]    = useState(+(config.max_position_size_pct * 100).toFixed(1));
  const [watchlist,  setWatchlist]  = useState(config.watchlist.join(", "));
  const [saving,     setSaving]     = useState(false);
  const [license,    setLicense]    = useState(config.license_key);
  const [licState,   setLicState]   = useState<"idle"|"checking"|"ok"|"error">(config.license_key ? "ok" : "idle");
  const [licMsg,     setLicMsg]      = useState(config.license_key ? "License active." : "");

  const meta      = AI_PROVIDERS.find(p => p.value === provider) ?? AI_PROVIDERS[0];
  const modelList = AI_PROVIDER_MODELS[provider];
  const freeText  = modelList.length === 0;

  function changeProvider(next: Config["ai_provider"]) {
    setProvider(next);
    setAiModel(defaultModel(next));
  }

  async function validateLicense() {
    if (!isTauri()) { setLicState("error"); setLicMsg("Validation needs the desktop app."); return; }
    setLicState("checking");
    setLicMsg("Validating…");
    try {
      const result = await invoke<string>("check_license", { key: license.trim() });
      // Persist immediately — a validated key that isn't saved still blocks bot start.
      await invoke("save_config", { config: { ...config, license_key: license.trim() } });
      setLicMsg(result); setLicState("ok");
    } catch (err) {
      setLicMsg(String(err)); setLicState("error");
    }
  }

  async function handleSave() {
    setSaving(true);
    const updated: Config = {
      ...config,
      license_key:           license.trim(),
      t212_api_key:          t212Key.trim(),
      t212_api_secret:       t212Secret.trim(),
      t212_env:              env,
      t212_account_type:     acct,
      ai_provider:           provider,
      ai_api_key:            aiKey.trim(),
      ai_model:              aiModel.trim(),
      azure_endpoint:        provider === "azure" ? azureEp.trim() : config.azure_endpoint,
      stop_loss_pct:         stopLoss   / 100,
      take_profit_pct:       takeProfit / 100,
      max_open_positions:    maxPos,
      max_position_size_pct: maxSize    / 100,
      watchlist:             watchlist.split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
    };
    if (isTauri()) await invoke("save_config", { config: updated });
    setSaving(false);
    onSave(updated);
  }

  return (
    <div className="settings-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="settings-modal">
        <h2>⚙ Settings</h2>

        <div className="settings-section">
          <h3>License</h3>
          <div className="field">
            <label>License Key</label>
            <input
              type="text"
              value={license}
              onChange={e => { setLicense(e.target.value); setLicState("idle"); setLicMsg(""); }}
              placeholder="Paste your license key"
              style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}
            />
          </div>
          <div className="test-row">
            <button className="btn-primary" onClick={validateLicense}
              disabled={licState === "checking" || !license.trim()}>
              {licState === "checking" ? "Checking…" : "Validate Key"}
            </button>
            {licMsg && (
              <span className={`test-result ${licState === "ok" ? "ok" : licState === "error" ? "error" : "busy"}`}>
                {licMsg}
              </span>
            )}
          </div>
        </div>

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
            <select value={provider} onChange={e => changeProvider(e.target.value as Config["ai_provider"])}>
              {AI_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </div>
          {provider === "azure" && (
            <div className="field">
              <label>Azure Endpoint URL</label>
              <input type="text" value={azureEp} onChange={e => setAzureEp(e.target.value)}
                placeholder="https://your-resource.services.ai.azure.com/" />
            </div>
          )}
          <div className="field">
            <label>{meta.keyLabel}</label>
            <input type="password" value={aiKey} onChange={e => setAiKey(e.target.value)} placeholder={meta.keyPlaceholder} />
          </div>
          <div className="field">
            <label>Model{provider === "azure" ? " (deployment name)" : ""}</label>
            {freeText ? (
              <input type="text" value={aiModel} onChange={e => setAiModel(e.target.value)}
                placeholder={provider === "azure" ? "my-gpt-4o-deployment" : "llama3.2"} />
            ) : (
              <select value={aiModel} onChange={e => setAiModel(e.target.value)}>
                {modelList.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            )}
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
