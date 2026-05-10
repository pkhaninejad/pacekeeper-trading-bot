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

type ValidState = "idle" | "checking" | "ok" | "error";

export default function StepLicense({ config, setConfig, onNext, onBack }: Props) {
  const [key, setKey]       = useState(config.license_key);
  const [state, setState]   = useState<ValidState>(config.license_key ? "ok" : "idle");
  const [msg, setMsg]       = useState(config.license_key ? "License active." : "");

  async function handleValidate() {
    setState("checking");
    setMsg("Validating…");
    try {
      const result = await invoke<string>("check_license", { key: key.trim() });
      setMsg(result);
      setState("ok");
      setConfig({ ...config, license_key: key.trim() });
    } catch (err) {
      setMsg(String(err));
      setState("error");
    }
  }

  function handleNext() {
    setConfig({ ...config, license_key: key.trim() });
    onNext();
  }

  return (
    <div className="wizard-step">
      <WizardProgress current={2} total={6} />
      <h2>Activate Your License</h2>
      <p className="subtitle">
        Enter the license key you received after purchase. No key yet?{" "}
        <a href="mailto:khaninejad@gmail.com">Contact us</a> to get one.
      </p>

      <div className="field">
        <label>License Key</label>
        <input
          type="text"
          value={key}
          onChange={e => { setKey(e.target.value); setState("idle"); setMsg(""); }}
          placeholder="Paste your license key here"
          style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }}
        />
      </div>

      <div className="test-row">
        <button
          className="btn-primary"
          onClick={handleValidate}
          disabled={state === "checking" || !key.trim()}
        >
          {state === "checking" ? "Checking…" : "Validate Key"}
        </button>
        {msg && (
          <span className={`test-result ${state === "ok" ? "ok" : state === "error" ? "error" : "busy"}`}>
            {msg}
          </span>
        )}
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleNext} disabled={state !== "ok"}>
          Next →
        </button>
      </div>
    </div>
  );
}
