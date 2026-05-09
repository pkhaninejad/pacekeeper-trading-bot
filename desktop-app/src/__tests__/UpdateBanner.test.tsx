import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: vi.fn(),
}));

import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import UpdateBanner from "../components/UpdateBanner";

const mockCheck = vi.mocked(check);
const mockRelaunch = vi.mocked(relaunch);

function makeUpdate(overrides: Record<string, unknown> = {}) {
  return {
    version: "0.2.0",
    body: "Bug fixes and improvements",
    downloadAndInstall: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockRelaunch.mockResolvedValue(undefined);
});

test("renders nothing when no update is available", async () => {
  mockCheck.mockResolvedValue(null);
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(mockCheck).toHaveBeenCalled());
  expect(container.firstChild).toBeNull();
});

test("renders nothing when check throws (network error)", async () => {
  mockCheck.mockRejectedValue(new Error("network error"));
  const { container } = render(<UpdateBanner />);
  await waitFor(() => expect(mockCheck).toHaveBeenCalled());
  expect(container.firstChild).toBeNull();
});

test("renders banner when an update is available", async () => {
  mockCheck.mockResolvedValue(makeUpdate());
  render(<UpdateBanner />);
  await waitFor(() =>
    expect(screen.getByText(/Pacekeeper 0\.2\.0 is available/)).toBeInTheDocument()
  );
  expect(screen.getByText("Install & Restart")).toBeInTheDocument();
});

test("shows What's new toggle when update has body", async () => {
  mockCheck.mockResolvedValue(makeUpdate({ body: "New trading dashboard" }));
  render(<UpdateBanner />);
  await waitFor(() => expect(screen.getByText(/What's new/)).toBeInTheDocument());
});

test("clicking What's new expands release notes", async () => {
  mockCheck.mockResolvedValue(makeUpdate({ body: "New trading dashboard" }));
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText(/What's new/));
  fireEvent.click(screen.getByText(/What's new/));
  expect(screen.getByText("New trading dashboard")).toBeInTheDocument();
});

test("clicking Install & Restart calls downloadAndInstall then relaunch", async () => {
  const mockUpdate = makeUpdate();
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(mockUpdate.downloadAndInstall).toHaveBeenCalled());
  await waitFor(() => expect(mockRelaunch).toHaveBeenCalled());
});

test("clicking dismiss hides the banner", async () => {
  mockCheck.mockResolvedValue(makeUpdate());
  render(<UpdateBanner />);
  await waitFor(() => screen.getByLabelText("Dismiss"));
  fireEvent.click(screen.getByLabelText("Dismiss"));
  expect(screen.queryByText(/Pacekeeper 0\.2\.0 is available/)).not.toBeInTheDocument();
});

test("shows error state when install fails", async () => {
  const mockUpdate = makeUpdate({
    downloadAndInstall: vi.fn().mockRejectedValue(new Error("disk full")),
  });
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(screen.getByText(/Update failed/)).toBeInTheDocument());
  expect(screen.getByText("Retry")).toBeInTheDocument();
  expect(screen.getByText("Download manually ↗")).toBeInTheDocument();
});

test("dismiss is hidden while downloading", async () => {
  let resolveInstall!: () => void;
  const installPromise = new Promise<void>((resolve) => { resolveInstall = resolve; });
  const mockUpdate = makeUpdate({ downloadAndInstall: vi.fn().mockReturnValue(installPromise) });
  mockCheck.mockResolvedValue(mockUpdate);
  render(<UpdateBanner />);
  await waitFor(() => screen.getByText("Install & Restart"));
  fireEvent.click(screen.getByText("Install & Restart"));
  await waitFor(() => expect(screen.getByText(/Downloading/)).toBeInTheDocument());
  expect(screen.queryByLabelText("Dismiss")).not.toBeInTheDocument();
  resolveInstall();
});
