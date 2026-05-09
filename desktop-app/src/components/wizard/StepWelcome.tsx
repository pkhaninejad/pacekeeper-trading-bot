interface Props {
  onNext: () => void;
}

export default function StepWelcome({ onNext }: Props) {
  return (
    <div className="wizard-step">
      <h2>Welcome to Claude Trade Bot</h2>
      <p className="subtitle">
        Let's get your trading bot set up. We'll walk you through connecting
        your Trading 212 account, choosing an AI provider, and setting your
        risk limits. Takes about 5 minutes.
      </p>
      <div className="wizard-nav">
        <span />
        <button className="btn-primary" onClick={onNext}>Get Started →</button>
      </div>
    </div>
  );
}
