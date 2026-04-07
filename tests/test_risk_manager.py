"""Tests for RiskManager in src/bot/risk_manager.py."""

import pytest
from src.api.models import TradeSignal, Position, CashInfo
from src.bot.risk_manager import RiskManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_signal(**kwargs) -> TradeSignal:
    defaults = dict(
        ticker="AAPL", action="BUY", direction="LONG",
        confidence=0.8, reasoning="test", order_type="MARKET",
    )
    defaults.update(kwargs)
    return TradeSignal(**defaults)


def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=500.0, result=500.0, invested=19_500.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="AAPL", quantity=10, averagePrice=100, currentPrice=105, ppl=50)
    defaults.update(kwargs)
    return Position(**defaults)


# ---------------------------------------------------------------------------
# RiskManager.validate
# ---------------------------------------------------------------------------

class TestValidate:
    def setup_method(self):
        self.rm = RiskManager()

    def test_approved_simple_buy(self):
        signal = make_signal()
        cash = make_cash()
        approved, reason = self.rm.validate(signal, [], cash)
        assert approved is True
        assert reason == "Approved"

    def test_low_confidence_rejected(self):
        signal = make_signal(confidence=0.5)
        approved, reason = self.rm.validate(signal, [], make_cash())
        assert approved is False
        assert "Confidence" in reason

    def test_confidence_exactly_at_threshold_approved(self):
        signal = make_signal(confidence=0.6)
        approved, _ = self.rm.validate(signal, [], make_cash())
        assert approved is True

    def test_max_open_positions_rejected(self):
        # Fill up to max positions with different tickers
        positions = [make_position(ticker=f"TICK{i}") for i in range(10)]
        signal = make_signal(ticker="NEWT")  # new ticker not in positions
        approved, reason = self.rm.validate(signal, positions, make_cash())
        assert approved is False
        assert "Max open positions" in reason

    def test_max_positions_not_applied_to_close(self):
        positions = [make_position(ticker=f"TICK{i}") for i in range(10)]
        signal = make_signal(ticker="NEWT", action="SELL", direction="CLOSE")
        approved, _ = self.rm.validate(signal, positions, make_cash())
        assert approved is True

    def test_existing_position_not_counted_against_max(self):
        # If ticker already has a position, adding to it doesn't hit the new-position limit
        positions = [make_position(ticker=f"TICK{i}") for i in range(9)]
        positions.append(make_position(ticker="AAPL"))  # 10 total, but AAPL exists
        signal = make_signal(ticker="AAPL", direction="CLOSE")  # closing existing
        approved, _ = self.rm.validate(signal, positions, make_cash())
        assert approved is True

    def test_insufficient_cash_rejected(self):
        signal = make_signal(suggested_quantity=100.0, suggested_price=200.0)  # needs 20,000
        cash = make_cash(free=1_000.0)
        approved, reason = self.rm.validate(signal, [], cash)
        assert approved is False
        assert "Insufficient cash" in reason

    def test_sufficient_cash_approved(self):
        signal = make_signal(suggested_quantity=10.0, suggested_price=100.0)  # needs 1,000
        cash = make_cash(free=5_000.0)
        approved, _ = self.rm.validate(signal, [], cash)
        assert approved is True

    def test_position_auto_scaled_down(self):
        # Cash check runs before scaling, so free cash must cover the original quantity.
        # qty=5000 * price=100 = 500,000; free must be >= 500,000; total=1,000,000
        signal = make_signal(suggested_quantity=5_000.0, suggested_price=100.0)
        cash = make_cash(free=600_000.0, total=1_000_000.0)
        approved, _ = self.rm.validate(signal, [], cash)
        assert approved is True
        max_allowed = cash.total * self.rm.max_position_pct  # 50,000
        expected_qty = max_allowed / 100.0  # 500.0
        assert signal.suggested_quantity == pytest.approx(expected_qty)

    def test_short_position_auto_scaled_negative(self):
        signal = make_signal(
            direction="SHORT", suggested_quantity=-5_000.0, suggested_price=100.0
        )
        cash = make_cash()
        self.rm.validate(signal, [], cash)
        assert signal.suggested_quantity < 0  # still negative

    def test_no_doubling_long(self):
        positions = [make_position(ticker="AAPL", quantity=5)]  # already long
        signal = make_signal(ticker="AAPL", direction="LONG")
        approved, reason = self.rm.validate(signal, positions, make_cash())
        assert approved is False
        assert "Already long" in reason

    def test_no_doubling_short(self):
        positions = [make_position(ticker="AAPL", quantity=-5)]  # already short
        signal = make_signal(ticker="AAPL", action="BUY", direction="SHORT")
        approved, reason = self.rm.validate(signal, positions, make_cash())
        assert approved is False
        assert "Short selling is not supported" in reason

    def test_close_signal_bypasses_direction_check(self):
        positions = [make_position(ticker="AAPL", quantity=5)]
        signal = make_signal(ticker="AAPL", action="SELL", direction="CLOSE")
        approved, _ = self.rm.validate(signal, positions, make_cash())
        assert approved is True

    def test_close_signal_accepts_t212_ticker_match(self):
        positions = [make_position(ticker="AAPL_US_EQ", quantity=5)]
        signal = make_signal(ticker="AAPL", action="SELL", direction="CLOSE")
        approved, _ = self.rm.validate(signal, positions, make_cash())
        assert approved is True

    def test_close_signal_without_position_is_allowed(self):
        signal = make_signal(ticker="AAPL", action="SELL", direction="CLOSE")
        approved, _ = self.rm.validate(signal, [], make_cash())
        assert approved is True

    def test_new_short_signal_rejected(self):
        signal = make_signal(ticker="TSLA", action="SELL", direction="SHORT")
        approved, reason = self.rm.validate(signal, [], make_cash())
        assert approved is False
        assert "Short selling is not supported" in reason


# ---------------------------------------------------------------------------
# RiskManager.compute_quantity
# ---------------------------------------------------------------------------

class TestComputeQuantity:
    def setup_method(self):
        self.rm = RiskManager()

    def test_long_quantity_positive(self):
        signal = make_signal(direction="LONG")
        cash = make_cash(total=10_000.0)
        qty = self.rm.compute_quantity(signal, cash, current_price=100.0)
        # max_value = 10,000 * 0.05 = 500; qty = 500 / 100 = 5
        assert qty == pytest.approx(5.0)
        assert qty > 0

    def test_short_quantity_negative(self):
        signal = make_signal(direction="SHORT")
        cash = make_cash(total=10_000.0)
        qty = self.rm.compute_quantity(signal, cash, current_price=100.0)
        assert qty == pytest.approx(-5.0)
        assert qty < 0

    def test_quantity_rounded_to_4_decimals(self):
        signal = make_signal(direction="LONG")
        cash = make_cash(total=10_000.0)
        qty = self.rm.compute_quantity(signal, cash, current_price=3.0)
        # 500 / 3 = 166.6667 → rounds to 166.6667
        assert qty == round(500.0 / 3.0, 4)


# ---------------------------------------------------------------------------
# RiskManager.check_stop_loss
# ---------------------------------------------------------------------------

class TestCheckStopLoss:
    def setup_method(self):
        self.rm = RiskManager()  # stop_loss_pct = 0.02

    def test_long_stop_loss_triggered(self):
        # avg=100, current=97 → loss = 3% >= 2%
        pos = make_position(averagePrice=100, currentPrice=97)
        assert self.rm.check_stop_loss(pos) is True

    def test_long_stop_loss_not_triggered(self):
        # avg=100, current=99 → loss = 1% < 2%
        pos = make_position(averagePrice=100, currentPrice=99)
        assert self.rm.check_stop_loss(pos) is False

    def test_long_stop_loss_exactly_at_threshold(self):
        pos = make_position(averagePrice=100, currentPrice=98)
        assert self.rm.check_stop_loss(pos) is True

    def test_short_stop_loss_triggered(self):
        # short: avg=100, current=103 → loss = 3% >= 2%
        pos = make_position(quantity=-10, averagePrice=100, currentPrice=103, ppl=-30)
        assert self.rm.check_stop_loss(pos) is True

    def test_short_stop_loss_not_triggered(self):
        pos = make_position(quantity=-10, averagePrice=100, currentPrice=101, ppl=-10)
        assert self.rm.check_stop_loss(pos) is False


# ---------------------------------------------------------------------------
# RiskManager.check_take_profit
# ---------------------------------------------------------------------------

class TestCheckTakeProfit:
    def setup_method(self):
        self.rm = RiskManager()  # take_profit_pct = 0.04

    def test_long_take_profit_triggered(self):
        # avg=100, current=105 → gain = 5% >= 4%
        pos = make_position(averagePrice=100, currentPrice=105)
        assert self.rm.check_take_profit(pos) is True

    def test_long_take_profit_not_triggered(self):
        # avg=100, current=103 → gain = 3% < 4%
        pos = make_position(averagePrice=100, currentPrice=103)
        assert self.rm.check_take_profit(pos) is False

    def test_long_take_profit_exactly_at_threshold(self):
        pos = make_position(averagePrice=100, currentPrice=104)
        assert self.rm.check_take_profit(pos) is True

    def test_short_take_profit_triggered(self):
        # short: avg=100, current=95 → gain = 5% >= 4%
        pos = make_position(quantity=-10, averagePrice=100, currentPrice=95, ppl=50)
        assert self.rm.check_take_profit(pos) is True

    def test_short_take_profit_not_triggered(self):
        pos = make_position(quantity=-10, averagePrice=100, currentPrice=97, ppl=30)
        assert self.rm.check_take_profit(pos) is False


# ---------------------------------------------------------------------------
# RiskManager earnings window gate
# ---------------------------------------------------------------------------

from datetime import date, timedelta
from src.data.earnings_calendar import EarningsInfo


def make_earnings_info(ticker: str, in_window: bool) -> dict:
    return {
        ticker: EarningsInfo(
            ticker=ticker,
            earnings_date=date.today() + timedelta(days=1) if in_window else date.today() + timedelta(days=30),
            days_until=1 if in_window else 30,
            in_window=in_window,
            source="yfinance",
        )
    }


class TestEarningsWindow:
    def setup_method(self):
        self.rm = RiskManager()

    def test_buy_blocked_during_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("AAPL", in_window=True)
        approved, reason = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is False
        assert "earnings" in reason.lower()

    def test_close_allowed_during_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="SELL", direction="CLOSE")
        earnings = make_earnings_info("AAPL", in_window=True)
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True

    def test_buy_allowed_outside_earnings_window(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("AAPL", in_window=False)
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True

    def test_no_earnings_info_does_not_block(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=None)
        assert approved is True

    def test_ticker_not_in_earnings_dict_does_not_block(self):
        signal = make_signal(ticker="AAPL", action="BUY", direction="LONG")
        earnings = make_earnings_info("TSLA", in_window=True)  # different ticker
        approved, _ = self.rm.validate(signal, [], make_cash(), earnings_info=earnings)
        assert approved is True
