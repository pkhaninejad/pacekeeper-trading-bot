import { Config } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onNext: () => void;
  onBack: () => void;
}

export default function StepLicense({ onNext, onBack }: Props) {
  return (
    <div className="wizard-step">
      <WizardProgress current={2} total={6} />
      <h2>Register Your Free Copy</h2>
      <p className="subtitle">
        Pacekeeper is free — no license key needed. Please{" "}
        <a href="https://wallstrdev.com/product/pacekeeper-ai-trading-bot-suite-for-trading212-prediction-markets/"
          target="_blank" rel="noreferrer">register and place a free order</a>{" "}
        on wallstrdev.com so we can send you updates and support.
      </p>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={onNext}>Next →</button>
      </div>
    </div>
  );
}
