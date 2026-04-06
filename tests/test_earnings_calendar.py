"""Tests for EarningsCalendar in src/data/earnings_calendar.py."""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from src.data.earnings_calendar import EarningsCalendar, EarningsInfo, _cache


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


class TestFetchYfinance:
    def setup_method(self):
        _cache.clear()

    def test_returns_earnings_info_from_yfinance(self):
        future_date = date.today() + timedelta(days=10)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [future_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            info = cal.get_next_earnings("AAPL")

        assert info == future_date

    def test_in_window_true_when_earnings_tomorrow(self):
        tomorrow = date.today() + timedelta(days=1)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [tomorrow]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is True

    def test_not_in_window_when_earnings_far_away(self):
        far_date = date.today() + timedelta(days=30)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [far_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is False

    def test_in_window_true_when_earnings_yesterday(self):
        yesterday = date.today() - timedelta(days=1)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [yesterday]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar(days_before=2, days_after=1)
            assert cal.is_earnings_window("AAPL") is True

    def test_returns_none_when_calendar_missing_key(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            info = cal.get_next_earnings("AAPL")

        assert info is None

    def test_returns_none_when_yfinance_raises(self):
        with patch("src.data.earnings_calendar.yf.Ticker", side_effect=Exception("network error")):
            cal = EarningsCalendar()
            info = cal.get_next_earnings("AAPL")

        assert info is None

    def test_result_cached_second_call_skips_network(self):
        future_date = date.today() + timedelta(days=5)
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [future_date]}

        with patch("src.data.earnings_calendar.yf.Ticker", return_value=mock_ticker) as mock_yf:
            cal = EarningsCalendar()
            cal.get_next_earnings("AAPL")
            cal.get_next_earnings("AAPL")
            assert mock_yf.call_count == 1  # only fetched once
