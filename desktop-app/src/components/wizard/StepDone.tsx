import { useEffect } from "react";

interface Props {
  onComplete: () => void;
}

export default function StepDone({ onComplete }: Props) {
  useEffect(() => {
    const timer = setTimeout(onComplete, 2000);
    return () => clearTimeout(timer);
  }, [onComplete]);

  return (
    <div className="wizard-step done-screen">
      <div className="check">✓</div>
      <h2>You're all set!</h2>
      <p>Your bot is configured and ready to trade. Starting the launcher…</p>
    </div>
  );
}
