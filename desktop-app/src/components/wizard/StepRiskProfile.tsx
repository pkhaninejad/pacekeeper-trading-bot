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
  const [stopLoss,   setStopLoss]   = useState(+(config.stop_loss_pct   * 100).toFixed(1));
  const [takeProfit, setTakeProfit] = useState(+(config.take_profit_pct * 100).toFixed(1));
  const [maxPos,     setMaxPos]     = useState(config.max_open_positions);
  const [maxSize,    setMaxSize]    = useState(+(config.max_position_size_pct * 100).toFixed(1));

  function handleNext() {
    setConfig({
      ...config,
      stop_loss_pct:         stopLoss   / 100,
      take_profit_pct:       takeProfit / 100,
      max_open_positions:    maxPos,
      max_position_size_pct: maxSize    / 100,
    });
    onNext();
  }

  return (
    <div className="wizard-step">
      <WizardProgress current={5} total={6} />
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
