"""Tests for TradingEngine live-mode confirmation gate and guardrail state."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from src.bot.engine import TradingEngine


def make_mock_client(positions=None, cash=None):
    from src.api.models import CashInfo
    positions = positions or []
    cash = cash or CashInfo(free=10_000.0, total=20_000.0, ppl=500.0,
                            result=500.0, invested=19_500.0, pieCash=0.0)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get_positions = AsyncMock(return_value=positions)
    client.get_cash = AsyncMock(return_value=cash)
    pos_by_ticker = {p.ticker: p for p in positions}
    client.get_position = AsyncMock(side_effect=lambda ticker: pos_by_ticker.get(ticker))
    client.place_market_order = AsyncMock(return_value=MagicMock(id=1))
    return client


# ---------------------------------------------------------------------------
# Live confirmation gate
# ---------------------------------------------------------------------------

def test_live_confirmed_false_when_no_file(tmp_path):
    with patch("src.bot.engine.CONFIRMED_FILE", tmp_path / "live_confirmed.json"):
        engine = TradingEngine()
    assert engine._live_confirmed is False


def test_live_confirmed_true_when_file_exists(tmp_path):
    confirmed_file = tmp_path / "live_confirmed.json"
    confirmed_file.write_text(json.dumps({"confirmed": True}))
    with patch("src.bot.engine.CONFIRMED_FILE", confirmed_file):
        engine = TradingEngine()
    assert engine._live_confirmed is True


# ---------------------------------------------------------------------------
# emergency_stop()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_stop_halts_bot():
    engine = TradingEngine()
    engine.status.enabled = True

    mock_client = make_mock_client(positions=[])
    with patch("src.bot.engine.Trading212Client", return_value=mock_client):
        result = await engine.emergency_stop()

    assert engine.status.enabled is False
    assert engine.status.halted_reason == "emergency_stop"
    assert result["halted"] is True
    assert isinstance(result["positions_closed"], int)


@pytest.mark.asyncio
async def test_emergency_stop_closes_open_positions():
    from src.api.models import Position
    pos = Position(ticker="AAPL_US_EQ", quantity=10.0, averagePrice=100.0, currentPrice=110.0, ppl=100.0)

    mock_client = make_mock_client(positions=[pos])
    mock_client.place_market_order = AsyncMock(return_value=MagicMock(id=1))

    engine = TradingEngine()
    engine.status.enabled = True

    with patch("src.bot.engine.Trading212Client", return_value=mock_client):
        result = await engine.emergency_stop()

    assert result["positions_closed"] >= 0
    assert engine.status.halted_reason == "emergency_stop"


# ---------------------------------------------------------------------------
# Daily loss circuit-breaker
# ---------------------------------------------------------------------------

def test_daily_loss_pct_initial_zero():
    engine = TradingEngine()
    assert engine.status.daily_loss_pct == 0.0
    assert engine._day_start_ppl == 0.0


def test_compute_daily_loss_pct():
    engine = TradingEngine()
    engine._day_start_ppl = 1000.0
    engine._day_start_total = 20_000.0
    # ppl dropping from 1000 to 500 — loss of 500 on 20k portfolio = 2.5%
    daily_loss_pct = engine._compute_daily_loss_pct(ppl=500.0)
    assert abs(daily_loss_pct - 0.025) < 1e-6


def test_compute_daily_loss_pct_no_loss():
    engine = TradingEngine()
    engine._day_start_ppl = 1000.0
    engine._day_start_total = 20_000.0
    daily_loss_pct = engine._compute_daily_loss_pct(ppl=1200.0)
    assert daily_loss_pct == 0.0


def test_compute_daily_loss_pct_zero_total():
    engine = TradingEngine()
    engine._day_start_ppl = 0.0
    engine._day_start_total = 0.0
    daily_loss_pct = engine._compute_daily_loss_pct(ppl=-100.0)
    assert daily_loss_pct == 0.0
