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
  expect(screen.getByText("Welcome to Claude Trade Bot")).toBeInTheDocument();
});

test("Get Started advances to T212 step", () => {
  render(<SetupWizard initialConfig={DEFAULT_CONFIG} onComplete={vi.fn()} />);
  fireEvent.click(screen.getByText("Get Started →"));
  expect(screen.getByText("Connect Trading 212")).toBeInTheDocument();
});

test("resumes from setup_step if setup_complete is false", () => {
  const partial = { ...DEFAULT_CONFIG, setup_step: 2, setup_complete: false };
  render(<SetupWizard initialConfig={partial} onComplete={vi.fn()} />);
  // setup_step: 2 = AI Provider was last saved; resumeStep = 2+1 = 3 = Risk Profile
  expect(screen.getByText("Risk Profile")).toBeInTheDocument();
});
