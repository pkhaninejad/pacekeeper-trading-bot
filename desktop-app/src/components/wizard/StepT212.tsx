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
      <WizardProgress current={3} total={6} />
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
