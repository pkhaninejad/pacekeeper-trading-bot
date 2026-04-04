"""Tests for ClaudeStrategy in src/bot/strategy.py."""

import json
import pytest
from unittest.mock import MagicMock, patch
from src.api.models import Position, CashInfo, Instrument, TradeSignal
from src.bot.strategy import _build_market_context, ClaudeStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=5_000.0, total=10_000.0, ppl=200.0, result=200.0, invested=9_800.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="AAPL", quantity=10, averagePrice=150, currentPrice=155, ppl=50)
    defaults.update(kwargs)
    return Position(**defaults)


def make_instrument(ticker: str, name: str) -> Instrument:
    return Instrument(ticker=ticker, name=name)


# ---------------------------------------------------------------------------
# _build_market_context
# ---------------------------------------------------------------------------

class TestBuildMarketContext:
    def test_includes_free_cash(self):
        cash = make_cash(free=7_500.0)
        ctx = _build_market_context([], cash, ["AAPL"], [])
        assert "7500" in ctx

    def test_includes_watchlist_tickers(self):
        ctx = _build_market_context([], make_cash(), ["AAPL", "TSLA"], [])
        assert "AAPL" in ctx
        assert "TSLA" in ctx

    def test_includes_position_summary(self):
        pos = make_position(ticker="NVDA", quantity=5, averagePrice=500, currentPrice=525, ppl=125)
        ctx = _build_market_context([pos], make_cash(), ["NVDA"], [])
        assert "NVDA" in ctx
        assert "LONG" in ctx

    def test_short_position_labeled(self):
        pos = make_position(ticker="TSLA", quantity=-3, averagePrice=200, currentPrice=190, ppl=30)
        ctx = _build_market_context([pos], make_cash(), ["TSLA"], [])
        assert "SHORT" in ctx

    def test_no_positions_shows_none(self):
        ctx = _build_market_context([], make_cash(), ["AAPL"], [])
        assert "(none)" in ctx

    def test_instrument_names_included(self):
        instruments = [make_instrument("AAPL", "Apple Inc.")]
        ctx = _build_market_context([], make_cash(), ["AAPL"], instruments)
        assert "Apple Inc." in ctx

    def test_watchlist_ticker_not_in_instruments_uses_ticker_as_name(self):
        ctx = _build_market_context([], make_cash(), ["UNKN"], [])
        assert "UNKN" in ctx


# ---------------------------------------------------------------------------
# ClaudeStrategy.generate_signals
# ---------------------------------------------------------------------------

class TestGenerateSignals:
    def _make_strategy(self, raw_response: str) -> ClaudeStrategy:
        """Return a ClaudeStrategy with a mocked Anthropic client."""
        strategy = ClaudeStrategy.__new__(ClaudeStrategy)
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=raw_response)]
        mock_client.messages.create.return_value = mock_message
        strategy._client = mock_client
        return strategy

    def test_valid_json_array_parsed(self):
        payload = json.dumps([{
            "ticker": "AAPL", "action": "BUY", "direction": "LONG",
            "confidence": 0.85, "reasoning": "bullish", "order_type": "MARKET",
        }])
        strategy = self._make_strategy(payload)
        signals = strategy.generate_signals([], make_cash(), ["AAPL"], [])
        assert len(signals) == 1
        assert signals[0].ticker == "AAPL"
        assert signals[0].confidence == 0.85

    def test_single_dict_wrapped_in_list(self):
        payload = json.dumps({
            "ticker": "TSLA", "action": "SELL", "direction": "CLOSE",
            "confidence": 0.9, "reasoning": "take profit", "order_type": "MARKET",
        })
        strategy = self._make_strategy(payload)
        signals = strategy.generate_signals([], make_cash(), ["TSLA"], [])
        assert len(signals) == 1
        assert signals[0].ticker == "TSLA"

    def test_markdown_code_fence_stripped(self):
        payload = "```json\n" + json.dumps([{
            "ticker": "NVDA", "action": "BUY", "direction": "LONG",
            "confidence": 0.75, "reasoning": "gpu demand", "order_type": "MARKET",
        }]) + "\n```"
        strategy = self._make_strategy(payload)
        signals = strategy.generate_signals([], make_cash(), ["NVDA"], [])
        assert len(signals) == 1
        assert signals[0].ticker == "NVDA"

    def test_invalid_json_returns_empty(self):
        strategy = self._make_strategy("not valid json at all")
        signals = strategy.generate_signals([], make_cash(), ["AAPL"], [])
        assert signals == []

    def test_malformed_signal_skipped(self):
        payload = json.dumps([
            {"ticker": "AAPL", "action": "BUY", "direction": "LONG",
             "confidence": 0.8, "reasoning": "ok", "order_type": "MARKET"},
            {"this": "is", "missing": "required fields"},
        ])
        strategy = self._make_strategy(payload)
        signals = strategy.generate_signals([], make_cash(), ["AAPL"], [])
        assert len(signals) == 1  # malformed one skipped

    def test_api_exception_returns_empty(self):
        strategy = ClaudeStrategy.__new__(ClaudeStrategy)
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API down")
        strategy._client = mock_client
        signals = strategy.generate_signals([], make_cash(), ["AAPL"], [])
        assert signals == []

    def test_multiple_signals_returned(self):
        payload = json.dumps([
            {"ticker": "AAPL", "action": "BUY", "direction": "LONG",
             "confidence": 0.8, "reasoning": "momentum", "order_type": "MARKET"},
            {"ticker": "TSLA", "action": "BUY", "direction": "SHORT",
             "confidence": 0.7, "reasoning": "overbought", "order_type": "MARKET"},
        ])
        strategy = self._make_strategy(payload)
        signals = strategy.generate_signals([], make_cash(), ["AAPL", "TSLA"], [])
        assert len(signals) == 2
        tickers = {s.ticker for s in signals}
        assert tickers == {"AAPL", "TSLA"}
