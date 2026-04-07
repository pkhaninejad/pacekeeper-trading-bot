"""Tests for Pydantic models in src/api/models.py."""

import pytest
from datetime import datetime
from src.api.models import (
    Position, TradeSignal, CashInfo, Order, Instrument,
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, BotStatus,
    TradeOutcome, RegimeResult,
)


class TestPosition:
    def test_is_long(self):
        pos = Position(ticker="AAPL", quantity=10, averagePrice=100, currentPrice=105, ppl=50)
        assert pos.is_long is True
        assert pos.is_short is False

    def test_is_short(self):
        pos = Position(ticker="TSLA", quantity=-5, averagePrice=200, currentPrice=190, ppl=50)
        assert pos.is_short is True
        assert pos.is_long is False

    def test_pnl_pct_long_gain(self):
        pos = Position(ticker="AAPL", quantity=10, averagePrice=100, currentPrice=110, ppl=100)
        assert pos.pnl_pct == pytest.approx(10.0)

    def test_pnl_pct_long_loss(self):
        pos = Position(ticker="AAPL", quantity=10, averagePrice=100, currentPrice=90, ppl=-100)
        assert pos.pnl_pct == pytest.approx(-10.0)

    def test_pnl_pct_zero_avg_price(self):
        pos = Position(ticker="AAPL", quantity=10, averagePrice=0, currentPrice=110, ppl=0)
        assert pos.pnl_pct == 0.0

    def test_market_value_long(self):
        pos = Position(ticker="AAPL", quantity=5, averagePrice=100, currentPrice=200, ppl=500)
        assert pos.market_value == pytest.approx(1000.0)

    def test_market_value_short(self):
        # Short positions have negative quantity; market_value uses abs()
        pos = Position(ticker="AAPL", quantity=-5, averagePrice=200, currentPrice=180, ppl=100)
        assert pos.market_value == pytest.approx(900.0)

    def test_optional_fields_default_none(self):
        pos = Position(ticker="NVDA", quantity=1, averagePrice=500, currentPrice=510, ppl=10)
        assert pos.fxPpl is None
        assert pos.maxBuy is None
        assert pos.maxSell is None


class TestTradeSignal:
    def test_timestamp_auto_set(self):
        signal = TradeSignal(
            ticker="AAPL", action="BUY", direction="LONG",
            confidence=0.8, reasoning="momentum",
        )
        assert signal.timestamp is not None
        assert isinstance(signal.timestamp, datetime)

    def test_default_order_type_is_market(self):
        signal = TradeSignal(
            ticker="MSFT", action="SELL", direction="CLOSE",
            confidence=0.75, reasoning="take profit",
        )
        assert signal.order_type == "MARKET"

    def test_optional_suggested_fields(self):
        signal = TradeSignal(
            ticker="GOOGL", action="BUY", direction="LONG",
            confidence=0.9, reasoning="breakout",
            suggested_quantity=5.0, suggested_price=150.0,
        )
        assert signal.suggested_quantity == 5.0
        assert signal.suggested_price == 150.0

    def test_confidence_stored_as_float(self):
        signal = TradeSignal(
            ticker="AMZN", action="HOLD", direction="LONG",
            confidence=0.55, reasoning="uncertain",
        )
        assert isinstance(signal.confidence, float)
        assert signal.confidence == 0.55

    def test_short_direction(self):
        signal = TradeSignal(
            ticker="NFLX", action="BUY", direction="SHORT",
            confidence=0.7, reasoning="bearish",
            suggested_quantity=-3.0,
        )
        assert signal.direction == "SHORT"
        assert signal.suggested_quantity == -3.0


class TestCashInfo:
    def test_basic_construction(self):
        cash = CashInfo(free=5000.0, total=10000.0, ppl=200.0, result=200.0, invested=9800.0, pieCash=0.0)
        assert cash.free == 5000.0
        assert cash.total == 10000.0


class TestOrderModels:
    def test_market_order_request(self):
        req = MarketOrderRequest(ticker="AAPL", quantity=10.0)
        assert req.ticker == "AAPL"
        assert req.quantity == 10.0

    def test_limit_order_request_defaults(self):
        req = LimitOrderRequest(ticker="TSLA", quantity=5.0, limitPrice=250.0)
        assert req.timeValidity == "DAY"

    def test_stop_order_request_gtc(self):
        req = StopOrderRequest(ticker="NVDA", quantity=2.0, stopPrice=600.0, timeValidity="GOOD_TILL_CANCEL")
        assert req.timeValidity == "GOOD_TILL_CANCEL"


class TestBotStatus:
    def test_defaults(self):
        status = BotStatus(enabled=True)
        assert status.total_trades_today == 0
        assert status.total_pnl == 0.0
        assert status.open_positions == 0
        assert status.signals_generated == 0
        assert status.environment == "demo"
        assert status.last_run is None
        assert status.next_run is None


class TestTradeOutcome:
    def test_defaults(self):
        outcome = TradeOutcome(
            ticker="NVDA", action="BUY", direction="LONG",
            confidence=0.8, opened_at=datetime(2026, 4, 6, 10, 0, 0),
        )
        assert outcome.outcome == "OPEN"
        assert outcome.pnl_pct is None
        assert outcome.closed_at is None

    def test_closed_outcome(self):
        now = datetime(2026, 4, 6, 12, 0, 0)
        outcome = TradeOutcome(
            ticker="AAPL", action="SELL", direction="SHORT",
            confidence=0.72, opened_at=datetime(2026, 4, 5, 10, 0, 0),
            outcome="SL_HIT", pnl_pct=-2.0, closed_at=now,
        )
        assert outcome.outcome == "SL_HIT"
        assert outcome.pnl_pct == -2.0
        assert outcome.closed_at == now

    def test_tp_hit_outcome(self):
        outcome = TradeOutcome(
            ticker="TSLA", action="BUY", direction="LONG",
            confidence=0.9, opened_at=datetime(2026, 4, 1, 9, 30, 0),
            outcome="TP_HIT", pnl_pct=4.1,
            closed_at=datetime(2026, 4, 3, 14, 0, 0),
        )
        assert outcome.outcome == "TP_HIT"
        assert outcome.pnl_pct == pytest.approx(4.1)


from src.api.models import RegimeResult, BotStatus

def test_regime_result_bull():
    r = RegimeResult(
        regime="BULL",
        spy_vs_200ema=3.5,
        vix=15.0,
        position_size_multiplier=1.0,
        description="Bull market",
    )
    assert r.regime == "BULL"
    assert r.position_size_multiplier == 1.0

def test_bot_status_has_regime_field():
    s = BotStatus(enabled=True, environment="demo")
    assert s.regime is None  # optional, defaults to None
    s.regime = "BEAR"
    assert s.regime == "BEAR"
