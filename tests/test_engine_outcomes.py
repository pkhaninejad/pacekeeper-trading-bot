"""Tests for TradingEngine outcome log — open/close lifecycle."""
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from src.bot.engine import TradingEngine
from src.api.models import CashInfo, Position, Order, TradeSignal, TradeOutcome


def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=500.0,
                    result=500.0, invested=19_500.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="NVDA_US_EQ", quantity=10.0,
                    averagePrice=100.0, currentPrice=104.0, ppl=40.0)
    defaults.update(kwargs)
    return Position(**defaults)


def make_order(**kwargs) -> Order:
    defaults = dict(id=1, ticker="NVDA_US_EQ", orderedQuantity=10.0)
    defaults.update(kwargs)
    return Order(**defaults)


def make_signal(**kwargs) -> TradeSignal:
    defaults = dict(ticker="NVDA", action="BUY", direction="LONG",
                    confidence=0.8, reasoning="test")
    defaults.update(kwargs)
    return TradeSignal(**defaults)


class TestOutcomeLogInit:
    def test_outcome_log_starts_empty(self):
        engine = TradingEngine()
        assert engine._outcome_log == []

    def test_outcome_log_property_returns_last_200(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        for i in range(250):
            engine._outcome_log.append(TradeOutcome(
                ticker="AAPL", action="BUY", direction="LONG",
                confidence=0.8, opened_at=now,
            ))
        assert len(engine.outcome_log) == 200


class TestExecuteSignalCreatesOpenOutcome:
    @pytest.mark.asyncio
    async def test_buy_signal_creates_open_outcome(self):
        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"
        signal = make_signal(ticker="NVDA", action="BUY", direction="LONG", confidence=0.8)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        await engine._execute_signal(mock_client, signal, make_cash(), [])

        assert len(engine._outcome_log) == 1
        o = engine._outcome_log[0]
        assert o.ticker == "NVDA"
        assert o.action == "BUY"
        assert o.direction == "LONG"
        assert o.confidence == 0.8
        assert o.outcome == "OPEN"
        assert o.pnl_pct is None
        assert o.closed_at is None

    @pytest.mark.asyncio
    async def test_failed_order_does_not_create_outcome(self):
        engine = TradingEngine()
        signal = make_signal()
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(side_effect=Exception("T212 error"))

        await engine._execute_signal(mock_client, signal, make_cash(), [])

        assert engine._outcome_log == []
