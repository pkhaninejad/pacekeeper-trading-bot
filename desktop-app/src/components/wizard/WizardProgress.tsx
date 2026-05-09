interface Props {
  current: number;
  total: number;
}

export default function WizardProgress({ current, total }: Props) {
  const pct = Math.round((current / total) * 100);
  return (
    <div className="wizard-progress">
      <div className="wizard-progress-label">Step {current} of {total}</div>
      <div className="wizard-progress-bar">
        <div className="wizard-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
