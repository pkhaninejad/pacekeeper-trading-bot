import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import SettingsPanel from "../components/SettingsPanel";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

const baseProps = {
  config: { ...DEFAULT_CONFIG, t212_api_key: "key123", setup_complete: true },
  onSave: vi.fn(),
  onClose: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  mockInvoke.mockResolvedValue(undefined);
});

test("renders with pre-populated T212 key", () => {
  render(<SettingsPanel {...baseProps} />);
  const inputs = screen.getAllByDisplayValue("key123");
  expect(inputs.length).toBeGreaterThan(0);
});

test("Save calls invoke save_config and onSave", async () => {
  render(<SettingsPanel {...baseProps} />);
  fireEvent.click(screen.getByText("Save Settings"));
  await waitFor(() => expect(mockInvoke).toHaveBeenCalledWith("save_config", expect.anything()));
  expect(baseProps.onSave).toHaveBeenCalled();
});

test("Cancel calls onClose without saving", () => {
  render(<SettingsPanel {...baseProps} />);
  fireEvent.click(screen.getByText("Cancel"));
  expect(baseProps.onClose).toHaveBeenCalled();
  expect(mockInvoke).not.toHaveBeenCalled();
});
