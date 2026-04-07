"""Tests for TradingEngine close/toggle methods."""
import pytest
import httpx
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
    positions = positions or []
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_positions = AsyncMock(return_value=positions)
    pos_by_ticker = {p.ticker: p for p in positions}
    client.get_position = AsyncMock(side_effect=lambda ticker: pos_by_ticker.get(ticker))
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

    @pytest.mark.asyncio
    async def test_close_position_not_owned_error_is_mapped_to_value_error(self):
        """If broker reports no owned shares, endpoint should treat it as no open position."""
        pos = make_position(ticker="FB_US_EQ", quantity=1.0)
        mock_client = make_mock_client(positions=[pos])
        request = httpx.Request("POST", "https://demo.trading212.com/api/v0/equity/orders/market")
        response = httpx.Response(
            400,
            request=request,
            json={
                "type": "/api-errors/selling-equity-not-owned",
                "detail": "Selling more equities than owned, owned: 0.0",
            },
        )
        mock_client.place_market_order = AsyncMock(
            side_effect=httpx.HTTPStatusError("bad request", request=request, response=response)
        )
        engine = TradingEngine()
        engine._ticker_map["FB"] = "FB_US_EQ"

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            with pytest.raises(ValueError, match="No open position for FB"):
                await engine.close_position("FB")


# ---------------------------------------------------------------------------
# close_all_positions()
# ---------------------------------------------------------------------------

class TestCloseAllPositions:
    @pytest.mark.asyncio
    async def test_close_all_logs_trades_and_pnl(self):
        """Two open positions: both logged, one PnL snapshot at the end."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0)
        cash = make_cash(ppl=800.0, total=20_800.0, invested=20_000.0)

        order1 = make_order(id=101, ticker="NVDA_US_EQ", orderedQuantity=-10.0)
        order2 = make_order(id=102, ticker="AAPL_US_EQ", orderedQuantity=-5.0)

        mock_client = make_mock_client(
            positions=[pos1, pos2],
            cash=cash,
        )
        # Return different orders for each call
        mock_client.place_market_order = AsyncMock(side_effect=[order1, order2])

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        # Both trades logged
        assert len(engine._trade_log) == 2
        assert engine._trade_log[0]["action"] == "MANUAL_CLOSE"
        assert engine._trade_log[1]["action"] == "MANUAL_CLOSE"

        # One PnL snapshot at the end
        assert len(engine._pnl_history) == 1
        assert engine._pnl_history[0]["ppl"] == 800.0

        # Result list
        assert len(results) == 2
        assert results[0]["status"] == "closed"
        assert results[1]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_close_all_handles_partial_failure(self):
        """If one position fails to close, error is captured; others still close."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=5.0)
        cash = make_cash()

        mock_client = make_mock_client(positions=[pos1, pos2], cash=cash)
        mock_client.place_market_order = AsyncMock(
            side_effect=[Exception("T212 error"), make_order(id=102)]
        )

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert results[0]["status"] == "error"
        assert results[1]["status"] == "closed"
        # Only successful close is logged
        assert len(engine._trade_log) == 1

    @pytest.mark.asyncio
    async def test_close_all_skips_zero_quantity_positions(self):
        """Zero-quantity entries are skipped and never sent as sell orders."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        pos2 = make_position(ticker="AAPL_US_EQ", quantity=0.0)
        cash = make_cash()

        mock_client = make_mock_client(positions=[pos1, pos2], cash=cash)
        mock_client.place_market_order = AsyncMock(return_value=make_order(id=101))

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert mock_client.place_market_order.await_count == 1
        assert results[0]["ticker"] == "NVDA"
        assert results[0]["status"] == "closed"
        assert results[1]["ticker"] == "AAPL"
        assert results[1]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_close_all_skips_when_live_position_is_missing(self):
        """If live lookup shows missing position, close-all should skip it."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        mock_client = make_mock_client(positions=[pos1], cash=make_cash())
        mock_client.get_position = AsyncMock(return_value=None)

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert results[0]["status"] == "skipped"
        assert results[0]["detail"] == "Position already closed"
        mock_client.place_market_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_all_skips_when_live_max_sell_is_zero(self):
        """Live quantity can be stale; maxSell=0 must skip close."""
        pos1 = make_position(ticker="NVDA_US_EQ", quantity=10.0)
        live_pos = make_position(ticker="NVDA_US_EQ", quantity=10.0, maxSell=0.0)
        mock_client = make_mock_client(positions=[pos1], cash=make_cash())
        mock_client.get_position = AsyncMock(return_value=live_pos)

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert results[0]["status"] == "skipped"
        assert results[0]["detail"] == "Position already closed"
        mock_client.place_market_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_all_not_owned_error_becomes_skipped(self):
        """Race after live check should be treated as skipped, not error."""
        pos1 = make_position(ticker="NFLX_US_EQ", quantity=2.0)
        mock_client = make_mock_client(positions=[pos1], cash=make_cash())
        request = httpx.Request("POST", "https://demo.trading212.com/api/v0/equity/orders/market")
        response = httpx.Response(
            400,
            request=request,
            json={
                "type": "/api-errors/selling-equity-not-owned",
                "detail": "Selling more equities than owned, owned: 0.0",
            },
        )
        mock_client.place_market_order = AsyncMock(
            side_effect=httpx.HTTPStatusError("bad request", request=request, response=response)
        )

        engine = TradingEngine()

        with patch("src.bot.engine.Trading212Client", return_value=mock_client):
            results = await engine.close_all_positions()

        assert results[0]["status"] == "skipped"
        assert results[0]["detail"] == "Position already closed"
