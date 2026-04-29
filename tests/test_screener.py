"""Unit tests for src/data/screener.py — no yfinance network calls."""
import pytest
from src.data.screener import ScreenCandidate, run_screener


def test_empty_universe():
    result = run_screener([], price_data={}, max_results=3)
    assert result == []


def _base_spy() -> dict:
    """SPY entry that never triggers rs_vs_spy on its own."""
    return {"current_price": 500.0, "high_52w": 520.0,
            "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
            "return_5d": 0.01}


def test_volume_spike_detected():
    price_data = {
        "PLTR": {
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,  # no RS signal
        },
        "AAPL": {
            "current_price": 200.0, "high_52w": 230.0,
            "current_volume": 800_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.00,  # below average volume, no signal
        },
        "SPY": _base_spy(),
    }
    results = run_screener(["PLTR", "AAPL"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "PLTR" in tickers
    assert "AAPL" not in tickers
    pltr = next(r for r in results if r.ticker == "PLTR")
    assert pltr.trigger == "volume_spike"
    assert pltr.score == 1.0
    assert "vol=" in pltr.details
    assert "× avg" in pltr.details
