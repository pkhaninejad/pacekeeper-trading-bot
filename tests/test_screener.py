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


def test_rs_vs_spy_detected():
    price_data = {
        "META": {
            "current_price": 600.0, "high_52w": 700.0,
            "current_volume": 500_000, "avg_volume_30d": 1_000_000,  # no vol spike
            "return_5d": 0.08,   # +8% 5-day
        },
        "GILD": {
            "current_price": 90.0, "high_52w": 110.0,
            "current_volume": 400_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.02,   # +2%, only 1pp above SPY — below threshold
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},   # SPY +5%
    }
    results = run_screener(["META", "GILD"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "META" in tickers    # +8% vs SPY +5% = +3pp, exactly at threshold
    assert "GILD" not in tickers
    meta = next(r for r in results if r.ticker == "META")
    assert meta.trigger == "rs_vs_spy"
    assert "RS=+" in meta.details
    assert "pp vs SPY" in meta.details
    # score = 0.5 + (3.0 / 10) = 0.8
    assert abs(meta.score - 0.8) < 0.01


def test_near_52w_high_detected():
    price_data = {
        "CRWD": {
            "current_price": 395.0, "high_52w": 400.0,   # 1.25% from 52w high
            "current_volume": 500_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,   # no RS signal
        },
        "IBM": {
            "current_price": 150.0, "high_52w": 200.0,   # 25% from 52w high — too far
            "current_volume": 300_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.00,
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    results = run_screener(["CRWD", "IBM"], price_data=price_data, max_results=5)
    tickers = [r.ticker for r in results]
    assert "CRWD" in tickers
    assert "IBM" not in tickers
    crwd = next(r for r in results if r.ticker == "CRWD")
    assert crwd.trigger == "near_52w_high"
    assert "% from 52w high" in crwd.details
    # gap_pct = (400 - 395) / 400 = 0.0125
    # score = 0.5 + (1 - 0.0125/0.02) * 0.5 = 0.5 + 0.375 * 0.5 = 0.6875
    assert abs(crwd.score - 0.6875) < 0.001


def test_multi_criterion_score():
    """Ticker matching volume_spike + rs_vs_spy should outscore single-criterion ticker."""
    price_data = {
        "PLTR": {  # volume spike only
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,
        },
        "META": {  # volume spike + rs_vs_spy
            "current_price": 600.0, "high_52w": 700.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.09,   # +9%, SPY +5% → RS = +4pp
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},
    }
    results = run_screener(["PLTR", "META"], price_data=price_data, max_results=5)
    assert len(results) == 2
    assert results[0].ticker == "META"
    assert results[1].ticker == "PLTR"
    assert results[0].score > results[1].score
    assert "volume_spike" in results[0].trigger
    assert "rs_vs_spy" in results[0].trigger


def test_max_results_limit():
    """Only top N candidates returned even if more qualify."""
    price_data = {
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    for sym in ["A", "B", "C", "D", "E"]:
        price_data[sym] = {
            "current_price": 100.0, "high_52w": 130.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.01,
        }
    results = run_screener(["A", "B", "C", "D", "E"], price_data=price_data, max_results=2)
    assert len(results) == 2


def test_watchlist_tickers_excluded():
    """Tickers in exclude list do not appear in results."""
    price_data = {
        "NVDA": {
            "current_price": 900.0, "high_52w": 950.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.10,
        },
        "AMZN": {
            "current_price": 200.0, "high_52w": 220.0,
            "current_volume": 5_000_000, "avg_volume_30d": 1_000_000,
            "return_5d": 0.10,
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.05},
    }
    results = run_screener(
        ["NVDA", "AMZN"],
        price_data=price_data,
        exclude=["NVDA"],
        max_results=5,
    )
    tickers = [r.ticker for r in results]
    assert "NVDA" not in tickers
    assert "AMZN" in tickers


def test_no_qualifying_tickers():
    """Returns empty list when nothing meets any threshold."""
    price_data = {
        "XYZ": {
            "current_price": 50.0, "high_52w": 100.0,
            "current_volume": 100_000, "avg_volume_30d": 1_000_000,  # low vol
            "return_5d": -0.05,   # negative return
        },
        "SPY": {"current_price": 500.0, "high_52w": 520.0,
                "current_volume": 80_000_000, "avg_volume_30d": 70_000_000,
                "return_5d": 0.01},
    }
    results = run_screener(["XYZ"], price_data=price_data, max_results=3)
    assert results == []
