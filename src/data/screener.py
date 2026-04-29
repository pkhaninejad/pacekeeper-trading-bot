"""
Dynamic watchlist screener.

Scores S&P 500 universe tickers against momentum criteria each trading cycle.
Returns up to max_results ScreenCandidate objects for injection into the Claude prompt.
Uses a 1-year yfinance batch fetch (cached 5 min). Pass price_data explicitly for tests.

price_data dict shape (per ticker, including "SPY"):
  {
    "TICKER": {
      "current_price": float,
      "high_52w": float,
      "current_volume": int,     # most recent day's volume
      "avg_volume_30d": int,     # 30-day average volume
      "return_5d": float,        # decimal, e.g. 0.05 means +5%
    },
    ...
  }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds
_screener_cache: dict = {}  # {"data": dict, "fetched_at": datetime}

SP500_TOP100: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "BRK-B", "LLY", "JPM",
    "AVGO", "V", "UNH", "XOM", "MA", "JNJ", "HD", "PG", "COST", "ABBV",
    "MRK", "BAC", "CRM", "CVX", "NFLX", "KO", "WMT", "ORCL", "AMD", "LIN",
    "ACN", "PM", "ADBE", "MCD", "CSCO", "TXN", "TMO", "ABT", "PEP", "DIS",
    "WFC", "AMGN", "INTU", "NEE", "QCOM", "DHR", "ISRG", "AMAT", "PFE", "SPGI",
    "IBM", "VZ", "HON", "SYK", "BX", "GS", "UBER", "UNP", "ELV", "LOW",
    "RTX", "T", "PANW", "BA", "CAT", "BKNG", "AXP", "SBUX", "BLK", "DE",
    "GILD", "MDLZ", "ADI", "MS", "CI", "REGN", "MMC", "ETN", "NOW", "LRCX",
    "TJX", "ZTS", "KLAC", "PLD", "AMT", "CB", "MO", "ICE", "SHW", "DXCM",
    "APH", "BSX", "CME", "EQIX", "HCA", "VRTX", "PLTR", "CRWD", "MSTR", "APP",
]


@dataclass
class ScreenCandidate:
    ticker: str
    trigger: str   # "volume_spike", "rs_vs_spy", "near_52w_high", or "+" combined
    score: float   # higher = stronger; used for ranking
    details: str   # injected verbatim into Claude prompt, e.g. "vol=4.2× avg"


def _fetch_screener_data(universe: list[str]) -> dict:
    """Fetch 1-year OHLCV for universe tickers + SPY. Implemented in Task 7."""
    return {}


def run_screener(
    universe: list[str],
    price_data: dict | None = None,
    exclude: list[str] | None = None,
    max_results: int = 3,
) -> list[ScreenCandidate]:
    """Score universe tickers and return top candidates.

    Args:
        universe:   List of ticker symbols to screen.
        price_data: Pre-fetched data dict (see module docstring for shape).
                    Pass None to fetch internally via yfinance (with cache).
        exclude:    Tickers to omit from results (pass settings.WATCHLIST).
        max_results: Maximum candidates to return.
    """
    if not universe:
        return []
    return []  # stub — criteria implemented in subsequent tasks
