import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import SetupWizard from "../components/wizard/SetupWizard";
import { DEFAULT_CONFIG } from "../types/config";

const mockInvoke = vi.mocked(invoke);

beforeEach(() => {
  vi.clearAllMocks();
  mockInvoke.mockResolvedValue(undefined);
});

test("starts on welcome screen", () => {
  render(<SetupWizard initialConfig={DEFAULT_CONFIG} onComplete={vi.fn()} />);
  expect(screen.getByText("Welcome to Pacekeeper")).toBeInTheDocument();
});

test("Get Started advances to License step", () => {
  render(<SetupWizard initialConfig={DEFAULT_CONFIG} onComplete={vi.fn()} />);
  fireEvent.click(screen.getByText("Get Started →"));
  expect(screen.getByText("Activate Your License")).toBeInTheDocument();
});

test("resumes from setup_step if setup_complete is false", () => {
  const partial = { ...DEFAULT_CONFIG, setup_step: 2, setup_complete: false };
  render(<SetupWizard initialConfig={partial} onComplete={vi.fn()} />);
  // setup_step: 2 = T212 was last saved; resumeStep = 2+1 = 3 = AI Provider
  expect(screen.getByText("AI Provider")).toBeInTheDocument();
});
