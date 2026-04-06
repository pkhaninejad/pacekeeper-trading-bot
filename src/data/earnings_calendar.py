"""
Earnings calendar — fetches next earnings dates and detects blackout windows.

Data sources (in priority order):
1. yfinance ticker.calendar — free, no key
2. Finnhub /calendar/earnings — free tier, requires FINNHUB_API_KEY

Results are cached per ticker for 24 hours (earnings dates don't change intraday).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24

_cache: dict[str, dict] = {}  # {ticker: {"data": EarningsInfo, "fetched_at": datetime}}


@dataclass
class EarningsInfo:
    ticker: str
    earnings_date: Optional[date]
    days_until: Optional[int]   # None when earnings_date is None
    in_window: bool
    source: Literal["yfinance", "finnhub", "unavailable"]


def _is_fresh(entry: dict) -> bool:
    age = (datetime.utcnow() - entry["fetched_at"]).total_seconds()
    return age < CACHE_TTL_HOURS * 3600


class EarningsCalendar:
    """Fetches and caches earnings dates; detects blackout windows."""

    def __init__(self, days_before: int = 2, days_after: int = 1, finnhub_api_key: str = ""):
        self.days_before = days_before
        self.days_after = days_after
        self._finnhub_api_key = finnhub_api_key

    def get_next_earnings(self, ticker: str) -> Optional[date]:
        """Return next earnings date for ticker, or None if unavailable."""
        info = self._fetch(ticker)
        return info.earnings_date

    def is_earnings_window(self, ticker: str) -> bool:
        """Return True if today is within the blackout window for ticker."""
        info = self._fetch(ticker)
        return info.in_window

    def get_earnings_info(self, tickers: list[str]) -> dict[str, EarningsInfo]:
        """Bulk-fetch earnings info for all tickers. Returns dict keyed by ticker."""
        return {ticker: self._fetch(ticker) for ticker in tickers}

    def _fetch(self, ticker: str) -> EarningsInfo:
        """Return cached or freshly fetched EarningsInfo."""
        if ticker in _cache and _is_fresh(_cache[ticker]):
            return _cache[ticker]["data"]

        info = self._fetch_yfinance(ticker)
        if info is None and self._finnhub_api_key:
            info = self._fetch_finnhub(ticker)
        if info is None:
            info = EarningsInfo(
                ticker=ticker, earnings_date=None, days_until=None,
                in_window=False, source="unavailable",
            )

        _cache[ticker] = {"data": info, "fetched_at": datetime.utcnow()}
        return info

    def _build_info(self, ticker: str, earnings_date: date, source: Literal["yfinance", "finnhub"]) -> EarningsInfo:
        """Compute days_until and in_window from an earnings date."""
        today = date.today()
        days_until = (earnings_date - today).days
        # days_until < 0 means earnings passed; window spans [−days_after, days_before]
        in_window = -self.days_after <= days_until <= self.days_before
        return EarningsInfo(
            ticker=ticker,
            earnings_date=earnings_date,
            days_until=days_until,
            in_window=in_window,
            source=source,
        )

    def _fetch_yfinance(self, ticker: str) -> Optional[EarningsInfo]:
        """Try yfinance ticker.calendar for next earnings date."""
        raise NotImplementedError

    def _fetch_finnhub(self, ticker: str) -> Optional[EarningsInfo]:
        """Try Finnhub /calendar/earnings for next earnings date."""
        raise NotImplementedError
