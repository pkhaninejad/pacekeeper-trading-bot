"""Tests for the stock bot StrategyRunner — issue #108."""
from datetime import datetime

import pytest

from src.api.models import CashInfo, Position, TradeSignal
from src.bot.strategy_runner import STOCK_SCHEMA, StockStrategyRunner
from strategy_kit import get_schema


def _signal(ticker="AAPL", confidence=0.7, qty=1.0, price=100.0,
            action="BUY", direction="LONG"):
    return TradeSignal(
        ticker=ticker,
        action=action,
        direction=direction,
        confidence=confidence,
        reasoning="test",
        suggested_quantity=qty,
        suggested_price=price,
        order_type="MARKET",
        timestamp=datetime.now(),
    )


def _position(ticker="AAPL", avg=100.0, current=100.0, qty=1.0):
    return Position(
        ticker=ticker, quantity=qty, averagePrice=avg,
        currentPrice=current, ppl=0.0,
    )


def _cash(free=100_000.0, total=100_000.0):
    return CashInfo(free=free, total=total, ppl=0.0, result=0.0,
                    invested=0.0, pieCash=0.0)


class TestSchema:
    def test_registered_under_stock_key(self):
        assert get_schema("stock") is STOCK_SCHEMA

    def test_has_required_keys(self):
        keys = {f.key for f in STOCK_SCHEMA.fields}
        required = {
            "MIN_CONFIDENCE", "MAX_POSITION_SIZE_PCT", "MAX_OPEN_POSITIONS",
            "STOP_LOSS_PCT", "TAKE_PROFIT_PCT", "WATCHLIST",
            "ENABLE_SCREENER", "BLOCK_NEW_POSITIONS_ON_EARNINGS",
            "BLOCK_NEW_POSITIONS_ON_MACRO",
        }
        assert required <= keys

    def test_params_fill_defaults(self):
        runner = StockStrategyRunner({"MIN_CONFIDENCE": 0.8})
        assert runner.params["MIN_CONFIDENCE"] == 0.8
        assert runner.params["STOP_LOSS_PCT"] == 0.02  # default


class TestRunConfidenceGate:
    def test_low_confidence_rejected_by_strict_strategy(self):
        signals = [_signal(confidence=0.65)]
        strict = StockStrategyRunner({"MIN_CONFIDENCE": 0.90})
        lenient = StockStrategyRunner({"MIN_CONFIDENCE": 0.50})
        assert strict.run(signals, [], _cash()) == []
        assert len(lenient.run(signals, [], _cash())) == 1

    def test_same_signals_two_param_sets_differ(self):
        # Issue #108 headline acceptance.
        signals = [
            _signal(ticker="AAPL", confidence=0.62),
            _signal(ticker="NVDA", confidence=0.75),
            _signal(ticker="MSFT", confidence=0.95),
        ]
        strict = StockStrategyRunner({"MIN_CONFIDENCE": 0.80})
        lenient = StockStrategyRunner({"MIN_CONFIDENCE": 0.60})
        strict_out = strict.run(signals, [], _cash())
        lenient_out = lenient.run(signals, [], _cash())
        assert len(strict_out) == 1          # only MSFT
        assert len(lenient_out) == 3         # all three
        assert strict_out != lenient_out


class TestRunMaxPositions:
    def test_max_open_positions_caps_batch(self):
        signals = [
            _signal(ticker="AAPL"), _signal(ticker="NVDA"), _signal(ticker="MSFT"),
        ]
        runner = StockStrategyRunner({"MAX_OPEN_POSITIONS": 2, "MIN_CONFIDENCE": 0.5})
        out = runner.run(signals, [], _cash())
        assert len(out) == 2


class TestRunWatchlist:
    def test_ticker_outside_watchlist_skipped(self):
        signals = [_signal(ticker="GME", confidence=0.9)]
        runner = StockStrategyRunner({"WATCHLIST": "AAPL,MSFT", "MIN_CONFIDENCE": 0.5})
        assert runner.run(signals, [], _cash()) == []

    def test_ticker_in_watchlist_kept(self):
        signals = [_signal(ticker="AAPL", confidence=0.9)]
        runner = StockStrategyRunner({"WATCHLIST": "AAPL,MSFT", "MIN_CONFIDENCE": 0.5})
        assert len(runner.run(signals, [], _cash())) == 1


class TestManageExits:
    def test_tight_stop_closes_more_than_loose(self):
        # Long position down 3%.
        positions = [_position(avg=100.0, current=97.0)]
        tight = StockStrategyRunner({"STOP_LOSS_PCT": 0.02, "TAKE_PROFIT_PCT": 0.50})
        loose = StockStrategyRunner({"STOP_LOSS_PCT": 0.10, "TAKE_PROFIT_PCT": 0.50})
        assert len(tight.manage_exits(positions)) == 1   # 3% loss >= 2% stop
        assert loose.manage_exits(positions) == []       # 3% loss < 10% stop

    def test_take_profit_triggers(self):
        positions = [_position(avg=100.0, current=105.0)]  # +5%
        runner = StockStrategyRunner({"STOP_LOSS_PCT": 0.02, "TAKE_PROFIT_PCT": 0.04})
        assert len(runner.manage_exits(positions)) == 1
