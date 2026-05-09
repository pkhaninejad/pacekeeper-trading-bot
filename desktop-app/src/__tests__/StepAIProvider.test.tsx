import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import StepAIProvider from "../components/wizard/StepAIProvider";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("Next disabled until test passes", () => {
  render(<StepAIProvider {...baseProps} />);
  expect(screen.getByText("Next →")).toBeDisabled();
});

test("provider selector updates key label", () => {
  render(<StepAIProvider {...baseProps} />);
  fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "openai" } });
  expect(screen.getByText("OpenAI API Key")).toBeInTheDocument();
});

test("successful test enables Next", async () => {
  mockInvoke.mockResolvedValueOnce("Connected — Anthropic API");
  render(<StepAIProvider {...baseProps} />);
  fireEvent.change(screen.getByPlaceholderText(/sk-ant/i), { target: { value: "sk-ant-xxx" } });
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Connected/));
  expect(screen.getByText("Next →")).not.toBeDisabled();
});
