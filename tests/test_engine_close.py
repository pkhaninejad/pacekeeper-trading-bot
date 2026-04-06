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


# ---------------------------------------------------------------------------
# close_position()
# ---------------------------------------------------------------------------

class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_position_logs_trade_and_pnl(self):
        """Successful close: trade logged, PnL snapshot appended."""
        pos = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        cash = make_cash(ppl=600.0, total=20_100.0, invested=19_500.0)
        order = make_order(id=99, ticker="NVDA_US_EQ", orderedQuantity=-10.0)
        mock_client = make_mock_client(positions=[pos], cash=cash, order=order)

        engine = TradingEngine()
        engine._ticker_map["NVDA"] = "NVDA_US_EQ"

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            result = await engine.close_position("NVDA")

        # Trade logged
        assert len(engine._trade_log) == 1
        entry = engine._trade_log[0]
        assert entry["action"] == "MANUAL_CLOSE"
        assert entry["ticker"] == "NVDA"
        assert entry["order_id"] == 99

        # PnL snapshot appended
        assert len(engine._pnl_history) == 1
        snap = engine._pnl_history[0]
        assert snap["ppl"] == 600.0
        assert snap["total"] == 20_100.0

        # Return value
        assert result["order_id"] == 99

    @pytest.mark.asyncio
    async def test_close_position_unknown_ticker_raises(self):
        """Ticker with no open position raises ValueError."""
        mock_client = make_mock_client(positions=[])
        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            with pytest.raises(ValueError, match="No open position for NVDA"):
                await engine.close_position("NVDA")

        # Nothing logged
        assert engine._trade_log == []
        assert engine._pnl_history == []
