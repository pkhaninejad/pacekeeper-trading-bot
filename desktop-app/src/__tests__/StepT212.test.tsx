import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import StepT212 from "../components/wizard/StepT212";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

test("Next button disabled until test passes", () => {
  render(<StepT212 {...baseProps} />);
  expect(screen.getByText("Next →")).toBeDisabled();
});

test("Test Connection calls invoke and shows success", async () => {
  mockInvoke.mockResolvedValueOnce("Connected — cash balance: 1234.56");
  render(<StepT212 {...baseProps} />);
  fireEvent.change(screen.getByPlaceholderText(/paste from/i), { target: { value: "mykey" } });
  fireEvent.change(screen.getByPlaceholderText(/secret/i), { target: { value: "mysecret" } });
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Connected/));
  expect(screen.getByText("Next →")).not.toBeDisabled();
});

test("Test Connection shows error message on failure", async () => {
  mockInvoke.mockRejectedValueOnce("Invalid API key or secret");
  render(<StepT212 {...baseProps} />);
  fireEvent.change(screen.getByPlaceholderText(/paste from/i), { target: { value: "badkey" } });
  fireEvent.change(screen.getByPlaceholderText(/secret/i), { target: { value: "badsecret" } });
  fireEvent.click(screen.getByText("Test Connection"));
  await waitFor(() => screen.getByText(/Invalid API key/));
  expect(screen.getByText("Next →")).toBeDisabled();
});
