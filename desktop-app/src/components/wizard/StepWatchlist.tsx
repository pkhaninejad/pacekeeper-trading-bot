import { useState } from "react";
import { Config } from "../../types/config";
import WizardProgress from "./WizardProgress";

interface Props {
  config: Config;
  setConfig: (c: Config) => void;
  onFinish: () => void;
  onBack: () => void;
}

const DEFAULTS = ["AAPL","TSLA","NVDA","MSFT","AMZN","GOOGL","META","AMD","JPM","V","UBER","PLTR"];

export default function StepWatchlist({ config, setConfig, onFinish, onBack }: Props) {
  const [tickers, setTickers] = useState<string[]>(config.watchlist);
  const [input,   setInput]   = useState("");

  function toggle(ticker: string) {
    setTickers(prev =>
      prev.includes(ticker) ? prev.filter(t => t !== ticker) : [...prev, ticker]
    );
  }

  function addTicker() {
    const t = input.trim().toUpperCase();
    if (t && !tickers.includes(t)) {
      setTickers(prev => [...prev, t]);
    }
    setInput("");
  }

  function removeTicker(ticker: string) {
    setTickers(prev => prev.filter(t => t !== ticker));
  }

  function handleFinish() {
    setConfig({ ...config, watchlist: tickers });
    onFinish();
  }

  const extras = tickers.filter(t => !DEFAULTS.includes(t));

  return (
    <div className="wizard-step">
      <WizardProgress current={6} total={6} />
      <h2>Watchlist</h2>
      <p className="subtitle">Choose the stocks the bot will monitor and trade. You can change this at any time in Settings.</p>

      <div className="watchlist-grid">
        {DEFAULTS.map(t => (
          <span key={t} className={`ticker-chip ${tickers.includes(t) ? "selected" : ""}`} onClick={() => toggle(t)}>
            {tickers.includes(t) ? "✓ " : ""}{t}
          </span>
        ))}
        {extras.map(t => (
          <span key={t} className="ticker-chip selected">
            {t}
            <button className="remove" onClick={() => removeTicker(t)}>×</button>
          </span>
        ))}
      </div>

      <div className="field">
        <label>Add a ticker</label>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && addTicker()}
          placeholder="Add ticker (e.g. SHOP) and press Enter"
        />
      </div>

      <div className="wizard-nav">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary" onClick={handleFinish} disabled={tickers.length === 0}>Finish Setup</button>
      </div>
    </div>
  );
}
