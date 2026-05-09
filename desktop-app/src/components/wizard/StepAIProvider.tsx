import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config, AI_PROVIDERS, AI_PROVIDER_MODELS, defaultModel } from "../../types/config";
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
  const [model, setModel]       = useState(config.ai_model || defaultModel(config.ai_provider));
  const [endpoint, setEndpoint] = useState(config.azure_endpoint);
  const [test, setTest]         = useState<TestState>("idle");
  const [msg, setMsg]           = useState("");

  const meta       = AI_PROVIDERS.find(p => p.value === provider) ?? AI_PROVIDERS[0];
  const modelList  = AI_PROVIDER_MODELS[provider];
  const isAzure    = provider === "azure";
  const freeText   = modelList.length === 0; // azure + ollama get a text input

  function changeProvider(next: Config["ai_provider"]) {
    setProvider(next);
    setModel(defaultModel(next));
    setTest("idle");
    setMsg("");
  }

  function resetTest() { setTest("idle"); setMsg(""); }

  function mergedConfig(): Config {
    return {
      ...config,
      ai_provider:    provider,
      ai_api_key:     key.trim(),
      ai_model:       model.trim(),
      azure_endpoint: isAzure ? endpoint.trim() : config.azure_endpoint,
    };
  }

  async function handleTest() {
    setTest("testing");
    setMsg("Testing connection…");
    try {
      const result = await invoke<string>("test_ai_connection", {
        provider,
        key: key.trim(),
        endpoint: isAzure ? endpoint.trim() : null,
        model:    isAzure ? model.trim()    : null,
      });
      setMsg(result);
      setTest("ok");
      setConfig(mergedConfig());
    } catch (err) {
      setMsg(String(err));
      setTest("error");
    }
  }

  function handleNext() {
    setConfig(mergedConfig());
    onNext();
  }

  const testDisabled =
    test === "testing" ||
    (provider !== "ollama" && !key) ||
    (isAzure && !endpoint);

  return (
    <div className="wizard-step">
      <WizardProgress current={3} total={5} />
      <h2>AI Provider</h2>
      <p className="subtitle">Choose the AI model that will generate trade signals. Anthropic (Claude) is recommended.</p>

      <div className="field">
        <label>Provider</label>
        <select value={provider} onChange={e => changeProvider(e.target.value as Config["ai_provider"])}>
          {AI_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </div>

      {isAzure && (
        <div className="field">
          <label>Azure Endpoint URL</label>
          <input
            type="text"
            value={endpoint}
            onChange={e => { setEndpoint(e.target.value); resetTest(); }}
            placeholder="https://your-resource.services.ai.azure.com/"
          />
        </div>
      )}

      <div className="field">
        <label>{meta.keyLabel}</label>
        <input
          type="password"
          value={key}
          onChange={e => { setKey(e.target.value); resetTest(); }}
          placeholder={meta.keyPlaceholder}
        />
      </div>

      <div className="field">
        <label>Model{isAzure ? " (deployment name)" : ""}</label>
        {freeText ? (
          <input
            type="text"
            value={model}
            onChange={e => setModel(e.target.value)}
            placeholder={isAzure ? "my-gpt-4o-deployment" : "llama3.2"}
          />
        ) : (
          <select value={model} onChange={e => setModel(e.target.value)}>
            {modelList.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        )}
      </div>

      <div className="test-row">
        <button className="btn-primary" onClick={handleTest} disabled={testDisabled}>
          {test === "testing" ? "Testing…" : "Test Connection"}
        </button>
        {msg && (
          <span className={`test-result ${test === "ok" ? "ok" : test === "error" ? "error" : "busy"}`}>
            {msg}
          </span>
        )}
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleNext} disabled={test !== "ok"}>Next →</button>
      </div>
    </div>
  );
}
