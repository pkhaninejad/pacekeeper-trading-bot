import { useEffect, useRef, useState } from "react";

interface Props {
  onComplete: () => void;
}

const DELAY = 2000;

export default function StepDone({ onComplete }: Props) {
  const callbackRef = useRef(onComplete);
  const [progress, setProgress] = useState(0);

  // Keep ref current without adding it as a dep that restarts the effect
  useEffect(() => { callbackRef.current = onComplete; });

  useEffect(() => {
    const start = Date.now();
    const tick = setInterval(() => {
      const pct = Math.min(((Date.now() - start) / DELAY) * 100, 100);
      setProgress(pct);
      if (pct >= 100) {
        clearInterval(tick);
        callbackRef.current();
      }
    }, 40);
    return () => clearInterval(tick);
  }, []); // intentionally empty — must only run once on mount

  return (
    <div className="wizard-step done-screen">
      <div className="check">✓</div>
      <h2>You're all set!</h2>
      <p>Your bot is configured and ready to trade.</p>
      <div className="launcher-progress">
        <div className="launcher-progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <p className="launching-label">Starting the launcher…</p>
    </div>
  );
}
