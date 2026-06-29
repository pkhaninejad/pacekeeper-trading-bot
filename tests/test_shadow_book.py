"""Tests for shadow (paper) execution of stock strategies — issue #109."""
from datetime import datetime

import pytest

from src.api.models import TradeSignal
from src.bot.shadow_book import ShadowHolding, run_shadow_strategy
from src.bot.strategy_runner import StockStrategyRunner
from strategy_kit.portfolio import ShadowPortfolio


def _signal(ticker="AAPL", confidence=0.8, qty=10.0, price=100.0):
    return TradeSignal(
        ticker=ticker, action="BUY", direction="LONG", confidence=confidence,
        reasoning="t", suggested_quantity=qty, suggested_price=price,
        order_type="MARKET", timestamp=datetime.now(),
    )


@pytest.fixture
async def portfolio(tmp_path):
    p = ShadowPortfolio(str(tmp_path / "shadow.db"))
    await p.initialize()
    return p


async def test_open_creates_virtual_trade_and_debits_bankroll(portfolio):
    await portfolio.seed_bankroll("s1", 10_000.0)
    # 10% cap lets the full 10 shares through (1000 = 10% of 10k) without scaling.
    runner = StockStrategyRunner({"MIN_CONFIDENCE": 0.5, "MAX_POSITION_SIZE_PCT": 0.10})
    holdings: dict[str, ShadowHolding] = {}

    result = await run_shadow_strategy(
        portfolio=portfolio, strategy_id="s1", runner=runner,
        signals=[_signal("AAPL", qty=10, price=100)],
        prices={"AAPL": 100.0}, holdings=holdings,
    )

    assert result["opened"] == 1
    assert "AAPL" in holdings
    assert holdings["AAPL"].quantity == pytest.approx(10.0)
    balance = (await portfolio.equity_curve("s1"))[-1].balance
    assert balance == pytest.approx(10_000.0 - 1_000.0)  # 10 * 100 cost


async def test_exit_on_stop_loss_closes_holding(portfolio):
    await portfolio.seed_bankroll("s1", 10_000.0)
    # Tight 2% stop; open at 100 then re-price to 97 (-3%).
    runner = StockStrategyRunner({"MIN_CONFIDENCE": 0.5, "STOP_LOSS_PCT": 0.02,
                                  "TAKE_PROFIT_PCT": 0.50, "MAX_POSITION_SIZE_PCT": 0.10})
    holdings: dict[str, ShadowHolding] = {}
    await run_shadow_strategy(
        portfolio=portfolio, strategy_id="s1", runner=runner,
        signals=[_signal("AAPL", qty=10, price=100)],
        prices={"AAPL": 100.0}, holdings=holdings,
    )
    assert "AAPL" in holdings

    result = await run_shadow_strategy(
        portfolio=portfolio, strategy_id="s1", runner=runner,
        signals=[], prices={"AAPL": 97.0}, holdings=holdings,
    )
    assert result["closed"] == 1
    assert "AAPL" not in holdings
    # Settled P&L reflected: -3 per share * 10 = -30 vs starting 10k.
    stats = await portfolio.stats("s1")
    assert stats.total_pnl == pytest.approx(-30.0)


async def test_no_duplicate_open_for_existing_holding(portfolio):
    await portfolio.seed_bankroll("s1", 10_000.0)
    runner = StockStrategyRunner({"MIN_CONFIDENCE": 0.5})
    holdings: dict[str, ShadowHolding] = {}
    await run_shadow_strategy(
        portfolio=portfolio, strategy_id="s1", runner=runner,
        signals=[_signal("AAPL")], prices={"AAPL": 100.0}, holdings=holdings,
    )
    result = await run_shadow_strategy(
        portfolio=portfolio, strategy_id="s1", runner=runner,
        signals=[_signal("AAPL")], prices={"AAPL": 100.0}, holdings=holdings,
    )
    assert result["opened"] == 0
    assert len(holdings) == 1
