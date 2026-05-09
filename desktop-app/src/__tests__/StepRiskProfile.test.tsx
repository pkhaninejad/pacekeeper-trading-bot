import { render, screen, fireEvent } from "@testing-library/react";
import StepRiskProfile from "../components/wizard/StepRiskProfile";
import { DEFAULT_CONFIG } from "../types/config";

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("renders default stop-loss and take-profit values", () => {
  render(<StepRiskProfile {...baseProps} />);
  // 2% stop-loss and 4% take-profit displayed as numbers
  const inputs = screen.getAllByRole("spinbutton");
  const values = inputs.map(i => (i as HTMLInputElement).value);
  expect(values).toContain("2");
  expect(values).toContain("4");
});

test("Next always enabled on this step", () => {
  render(<StepRiskProfile {...baseProps} />);
  expect(screen.getByText("Next →")).not.toBeDisabled();
});

test("clicking Next calls onNext", () => {
  render(<StepRiskProfile {...baseProps} />);
  fireEvent.click(screen.getByText("Next →"));
  expect(baseProps.onNext).toHaveBeenCalled();
});
