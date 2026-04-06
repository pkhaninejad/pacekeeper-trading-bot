"""Tests for TradingEngine close/toggle methods."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.bot.engine import TradingEngine
from src.api.models import CashInfo, Position, Order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cash(**kwargs) -> CashInfo:
    defaults = dict(free=10_000.0, total=20_000.0, ppl=500.0,
                    result=500.0, invested=19_500.0, pieCash=0.0)
    defaults.update(kwargs)
    return CashInfo(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(ticker="NVDA_US_EQ", quantity=10.0,
                    averagePrice=100.0, currentPrice=110.0, ppl=100.0)
    defaults.update(kwargs)
    return Position(**defaults)


def make_order(**kwargs) -> Order:
    defaults = dict(id=42, ticker="NVDA_US_EQ", orderedQuantity=10.0)
    defaults.update(kwargs)
    return Order(**defaults)


def make_mock_client(positions=None, cash=None, order=None):
    """Return a mock Trading212Client usable as async context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_positions = AsyncMock(return_value=positions or [])
    client.get_cash = AsyncMock(return_value=cash or make_cash())
    client.place_market_order = AsyncMock(return_value=order or make_order())
    return client


# ---------------------------------------------------------------------------
# toggle()
# ---------------------------------------------------------------------------

class TestToggle:
    def test_toggle_disable_does_not_set_running_false(self):
        """Pausing the bot must NOT kill the start() loop (_running stays True)."""
        engine = TradingEngine()
        engine._running = True

        engine.toggle()  # disable

        assert engine.status.enabled is False
        assert engine._running is True   # loop must still be alive

    def test_toggle_reenable_works(self):
        """Re-enabling after pause correctly sets enabled=True."""
        engine = TradingEngine()
        engine._running = True

        engine.toggle()   # disable
        engine.toggle()   # re-enable

        assert engine.status.enabled is True
        assert engine._running is True
