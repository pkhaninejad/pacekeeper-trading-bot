import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Config } from "../../types/config";
import StepWelcome     from "./StepWelcome";
import StepLicense     from "./StepLicense";
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
  // Resume past welcome only if a form step (step >= 1) was previously saved
  const resumeStep = (!initialConfig.setup_complete && initialConfig.setup_step >= 1)
    ? Math.min(initialConfig.setup_step + 1, 6)
    : 0;
  const [step, setStep]     = useState(resumeStep);
  const [config, setConfig] = useState<Config>(initialConfig);

  async function advance() {
    // Save progress only from form steps (step 1+); welcome has no data
    if (step >= 1) {
      const partial: Config = { ...config, setup_step: step, setup_complete: false };
      await invoke("save_config", { config: partial }).catch(() => {});
    }
    setStep(step + 1);
  }

  async function finish() {
    const final: Config = { ...config, setup_step: 6, setup_complete: true };
    await invoke("save_config", { config: final }).catch(() => {});
    setConfig(final);
    setStep(7);
  }

  return (
    <div className="wizard">
      {step === 0 && <StepWelcome    onNext={advance} />}
      {step === 1 && <StepLicense    config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(0)} />}
      {step === 2 && <StepT212       config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(1)} />}
      {step === 3 && <StepAIProvider config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(2)} />}
      {step === 4 && <StepRiskProfile config={config} setConfig={setConfig} onNext={advance} onBack={() => setStep(3)} />}
      {step === 5 && <StepWatchlist  config={config} setConfig={setConfig} onFinish={finish} onBack={() => setStep(4)} />}
      {step >= 6  && <StepDone onComplete={onComplete} />}
    </div>
  );
}
