import { render, screen, fireEvent } from "@testing-library/react";
import StepWatchlist from "../components/wizard/StepWatchlist";
import { DEFAULT_CONFIG } from "../types/config";

const baseProps = {
  config: { ...DEFAULT_CONFIG },
  setConfig: vi.fn(),
  onFinish: vi.fn(),
  onBack: vi.fn(),
};

beforeEach(() => vi.clearAllMocks());

test("renders default tickers", () => {
  render(<StepWatchlist {...baseProps} />);
  expect(screen.getByText(/AAPL/)).toBeInTheDocument();
  expect(screen.getByText(/TSLA/)).toBeInTheDocument();
});

test("Finish disabled when watchlist is empty", () => {
  const config = { ...DEFAULT_CONFIG, watchlist: [] };
  render(<StepWatchlist {...baseProps} config={config} />);
  expect(screen.getByText("Finish Setup")).toBeDisabled();
});

test("typing and pressing Enter adds a ticker", () => {
  render(<StepWatchlist {...baseProps} />);
  const input = screen.getByPlaceholderText(/add ticker/i);
  fireEvent.change(input, { target: { value: "HOOD" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByText(/HOOD/)).toBeInTheDocument();
});
