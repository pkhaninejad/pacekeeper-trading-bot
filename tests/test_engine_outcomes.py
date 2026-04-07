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


class TestUpdateOutcome:
    def test_updates_most_recent_open_for_ticker(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        engine._update_outcome("NVDA", "TP_HIT", pnl_pct=4.0)
        o = engine._outcome_log[0]
        assert o.outcome == "TP_HIT"
        assert o.pnl_pct == 4.0
        assert o.closed_at is not None

    def test_ignores_already_closed_outcomes(self):
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now, outcome="TP_HIT",
            pnl_pct=4.0, closed_at=now,
        ))
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.75, opened_at=now,
        ))
        engine._update_outcome("NVDA", "SL_HIT", pnl_pct=-2.0)
        assert engine._outcome_log[0].outcome == "TP_HIT"   # unchanged
        assert engine._outcome_log[1].outcome == "SL_HIT"

    def test_no_open_outcome_for_ticker_is_noop(self):
        engine = TradingEngine()
        engine._update_outcome("NVDA", "SL_HIT", pnl_pct=-2.0)  # must not raise
        assert engine._outcome_log == []


class TestManageExitsUpdatesOutcomes:
    @pytest.mark.asyncio
    async def test_stop_loss_sets_sl_hit(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=97.9, ppl=-21.0)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        with patch.object(engine.risk, "check_stop_loss", return_value=True):
            with patch.object(engine.risk, "check_take_profit", return_value=False):
                await engine._manage_exits(mock_client, [pos])

        o = engine._outcome_log[0]
        assert o.outcome == "SL_HIT"
        assert o.ticker == "NVDA"
        assert o.pnl_pct == pytest.approx(-2.1, abs=0.1)
        assert o.closed_at is not None

    @pytest.mark.asyncio
    async def test_take_profit_sets_tp_hit(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=104.0, ppl=40.0)
        mock_client = MagicMock()
        mock_client.place_market_order = AsyncMock(return_value=make_order())

        with patch.object(engine.risk, "check_stop_loss", return_value=False):
            with patch.object(engine.risk, "check_take_profit", return_value=True):
                await engine._manage_exits(mock_client, [pos])

        o = engine._outcome_log[0]
        assert o.outcome == "TP_HIT"
        assert o.pnl_pct == pytest.approx(4.0, abs=0.1)


class TestClosePositionUpdatesOutcome:
    @pytest.mark.asyncio
    async def test_close_position_sets_manual_close(self):
        from unittest.mock import patch
        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                            averagePrice=100.0, currentPrice=103.0, ppl=30.0)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_positions = AsyncMock(return_value=[pos])
        mock_client.get_cash = AsyncMock(return_value=make_cash())
        mock_client.place_market_order = AsyncMock(return_value=make_order(id=99))

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            await engine.close_position("NVDA")

        o = engine._outcome_log[0]
        assert o.outcome == "MANUAL_CLOSE"
        assert o.pnl_pct == pytest.approx(3.0, abs=0.1)
        assert o.closed_at is not None

    @pytest.mark.asyncio
    async def test_close_all_positions_sets_manual_close_for_each(self):
        from unittest.mock import patch
        engine = TradingEngine()
        now = datetime.now(UTC)
        engine._outcome_log.append(TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=now,
        ))
        engine._outcome_log.append(TradeOutcome(
            ticker="AAPL", action="BUY", direction="LONG",
            confidence=0.75, opened_at=now,
        ))
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0,
                             averagePrice=100.0, currentPrice=104.0, ppl=40.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0,
                             averagePrice=150.0, currentPrice=153.0, ppl=15.0)
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_positions = AsyncMock(return_value=[pos1, pos2])
        mock_client.get_cash = AsyncMock(return_value=make_cash())
        mock_client.place_market_order = AsyncMock(side_effect=[
            make_order(id=101), make_order(id=102),
        ])

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            await engine.close_all_positions()

        nvda_o = next(o for o in engine._outcome_log if o.ticker == "NVDA")
        aapl_o = next(o for o in engine._outcome_log if o.ticker == "AAPL")
        assert nvda_o.outcome == "MANUAL_CLOSE"
        assert aapl_o.outcome == "MANUAL_CLOSE"
