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
