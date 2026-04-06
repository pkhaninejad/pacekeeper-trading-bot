"""Tests for EarningsCalendar in src/data/earnings_calendar.py."""
from datetime import date, timedelta
from src.data.earnings_calendar import EarningsInfo


class TestEarningsInfo:
    def test_in_window_true(self):
        info = EarningsInfo(
            ticker="AAPL",
            earnings_date=date.today() + timedelta(days=1),
            days_until=1,
            in_window=True,
            source="yfinance",
        )
        assert info.in_window is True
        assert info.source == "yfinance"

    def test_unavailable_not_in_window(self):
        info = EarningsInfo(
            ticker="AAPL",
            earnings_date=None,
            days_until=None,
            in_window=False,
            source="unavailable",
        )
        assert info.earnings_date is None
        assert info.in_window is False
